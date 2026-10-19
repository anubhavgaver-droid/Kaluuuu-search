import asyncio
import html
import re
import time

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, InputUserDeactivated, PeerIdInvalid, UserIsBlocked
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import backup
import database as db
import texts
from config import Config
from delivery import reply_temp

admin = filters.user(Config.ADMINS) & filters.private
admin_any = filters.user(Config.ADMINS)


# ---------------- banned users are stopped before any other handler ----------------
async def _is_banned(_, __, update):
    u = getattr(update, "from_user", None)
    return bool(u) and u.id not in Config.ADMINS and db.is_banned(u.id)


banned = filters.create(_is_banned)


@Client.on_message(banned, group=-10)
async def block_message(client, message):
    message.stop_propagation()


@Client.on_callback_query(banned, group=-10)
async def block_callback(client, cq):
    await cq.answer("🚫 You are banned from using this bot.", show_alert=True)
    cq.stop_propagation()


def _target_user(message):
    """user id from '/ban 123' or from replying to someone's message"""
    if len(message.command) > 1 and message.command[1].lstrip("-").isdigit():
        return int(message.command[1]), " ".join(message.command[2:])
    r = message.reply_to_message
    if r and r.from_user:
        return r.from_user.id, " ".join(message.command[1:])
    return None, ""


@Client.on_message(filters.command("ban") & admin_any)
async def ban(client, message):
    uid, reason = _target_user(message)
    if not uid:
        return await message.reply_text("Usage: /ban <code>user_id [reason]</code> (or reply to their message)")
    if uid in Config.ADMINS:
        return await message.reply_text("❌ You can't ban an admin.")
    await db.ban_user(uid, reason)
    await message.reply_text(f"🚫 Banned <code>{uid}</code>.")


@Client.on_message(filters.command("unban") & admin_any)
async def unban(client, message):
    uid, _ = _target_user(message)
    if not uid:
        return await message.reply_text("Usage: /unban <code>user_id</code>")
    ok = await db.unban_user(uid)
    await message.reply_text(f"✅ Unbanned <code>{uid}</code>." if ok else "ℹ️ That user wasn't banned.")


# ---------------- broadcast ----------------
@Client.on_message(filters.command("broadcast") & admin)
async def broadcast(client, message):
    src = message.reply_to_message
    text = message.text.split(None, 1)[1] if len(message.command) > 1 else None
    if not src and not text:
        return await message.reply_text(
            "Usage: reply to any message with /broadcast, or send <code>/broadcast your text</code>.\n"
            "It goes only to people who started the bot."
        )
    users = [u for u in await db.all_user_ids() if not db.is_banned(u)]
    status = await message.reply_text(f"📣 Sending to {len(users)} users…")
    asyncio.create_task(_run_broadcast(client, src, text, users, status))


async def _run_broadcast(client, src, text, users, status):
    sent = blocked = failed = 0
    for i, uid in enumerate(users, 1):
        for attempt in (1, 2):
            try:
                if src:
                    await src.copy(uid)
                else:
                    await client.send_message(uid, text, disable_web_page_preview=True)
                sent += 1
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                if attempt == 1:
                    continue  # retry once after the wait
                failed += 1
            except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid):
                blocked += 1
                await db.remove_user(uid)  # gone - skip next time (they return by pressing /start)
            except Exception:
                failed += 1
            break
        if i % 50 == 0:
            try:
                await status.edit_text(f"📣 {i}/{len(users)}  ✅ {sent}  🚫 {blocked}  ⚠️ {failed}")
            except Exception:
                pass
        await asyncio.sleep(Config.BROADCAST_DELAY)
    try:
        await status.edit_text(f"✅ <b>Broadcast done</b>\n✅ Sent: {sent}\n🚫 Blocked/inactive (removed): {blocked}\n⚠️ Failed: {failed}")
    except Exception:
        pass


# ---------------- stats ----------------
@Client.on_message(filters.command("stats") & admin)
async def stats(client, message):
    now = time.time()
    top_ids = await db.trending(7, 5)
    top_stories = []
    for pid, n in top_ids:
        p = await db.get_post(pid)
        if p:
            top_stories.append((p["title"], n))
    d = {
        "posts": await db.count_posts(),
        "channels": len(await db.list_channels()),
        "users": await db.count_users(),
        "new24": await db.users_since(now - 86400),
        "new7": await db.users_since(now - 7 * 86400),
        "s1": await db.search_counts(1),
        "s7": await db.search_counts(7),
        "top_today": await db.top_searches(1, 5),
        "top_stories": top_stories,
        "pending": await db.count_pending(),
        "misses": await db.count_misses(),
        "bans": await db.count_bans(),
        "groups": len(await db.list_groups()),
    }
    await message.reply_text(texts.stats_box(d))


# ---------------- searches that found nothing ----------------
@Client.on_message(filters.command("missing") & admin)
async def missing(client, message):
    if len(message.command) > 1 and message.command[1].lower() == "clear":
        n = await db.clear_misses()
        return await message.reply_text(f"🧹 Cleared {n} entries.")
    await message.reply_text(texts.missing_list(await db.top_misses(25), await db.count_misses()))


# ---------------- allowed groups (managed live, stored in MongoDB) ----------------
GROUP_TYPES = ("GROUP", "SUPERGROUP")


async def _group_arg(client, message):
    """-> (chat id, title). No argument = the group the command was sent in; or pass -100id / @username / t.me link."""
    arg = message.command[1] if len(message.command) > 1 else None
    if not arg:
        if message.chat.type.name in GROUP_TYPES:
            return message.chat.id, message.chat.title or "Group"
        return None, None
    m = re.search(r"t\.me/([A-Za-z0-9_]{4,})", arg)
    ref = m.group(1) if m else arg.lstrip("@")
    try:
        ref = int(ref)
    except ValueError:
        pass
    try:
        chat = await client.get_chat(ref)
    except Exception:
        return (ref, "Group") if isinstance(ref, int) else (None, None)  # a raw id is still fine for /denygroup
    if chat.type.name not in GROUP_TYPES:
        return None, None
    return chat.id, chat.title or "Group"


async def _say(message, text):
    if message.chat.type.name == "PRIVATE":
        return await message.reply_text(text)
    return await reply_temp(message, text)  # in a group the reply cleans itself up


def _groups_keyboard(rows):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"🗑 {g.get('title', '?')[:35]}", callback_data=f"gd:{g['_id']}")] for g in rows[:20]]
    ) if rows else None


@Client.on_message(filters.command("allowgroup") & admin_any)
async def allow_group(client, message):
    chat_id, title = await _group_arg(client, message)
    if not chat_id:
        return await _say(message, "Usage: send /allowgroup inside the group, or /allowgroup <code>-100id</code> / <code>@username</code> here.")
    await db.allow_group(chat_id, title)
    await _say(message, f"✅ <b>{html.escape(title)}</b> is now allowed.\nThe bot works only in allowed groups from now on (see /groups).")


@Client.on_message(filters.command("denygroup") & admin_any)
async def deny_group(client, message):
    chat_id, title = await _group_arg(client, message)
    if not chat_id:
        return await _say(message, "Usage: send /denygroup inside the group, or /denygroup <code>-100id</code> / <code>@username</code> here.")
    await db.deny_group(chat_id)
    left = len(await db.list_groups())
    await _say(message, f"🚫 <b>{html.escape(title)}</b> removed." + ("" if left else "\nNo group is on the list now, so the bot works in every group again."))


@Client.on_message(filters.command("groups") & admin)
async def groups(client, message):
    rows = await db.list_groups()
    await message.reply_text(texts.groups_list(rows), reply_markup=_groups_keyboard(rows))


@Client.on_callback_query(filters.regex(r"^gd:"))
async def group_remove(client, cq):
    if cq.from_user.id not in Config.ADMINS:
        return await cq.answer("Admins only.", show_alert=True)
    await db.deny_group(int(cq.data[3:]))
    rows = await db.list_groups()
    try:
        await cq.message.edit_text(texts.groups_list(rows), reply_markup=_groups_keyboard(rows))
    except Exception:
        pass
    await cq.answer("Removed")


# ---------------- backup / restore ----------------
@Client.on_message(filters.command("backup") & admin)
async def backup_now(client, message):
    status = await message.reply_text("⏳ Creating backup…")
    try:
        await backup.send_backup(client, message.chat.id)
        await status.delete()
    except Exception as e:
        await status.edit_text(f"❌ Backup failed: {html.escape(str(e))}")


@Client.on_message(filters.command("restore") & admin)
async def restore(client, message):
    src = message.reply_to_message
    if not src or not src.document:
        return await message.reply_text("Reply to a backup file (.json.gz) with /restore.")
    status = await message.reply_text("⏳ Restoring…")
    try:
        f = await client.download_media(src, in_memory=True)
        counts = await backup.restore_backup(bytes(f.getbuffer()))
    except Exception as e:
        return await status.edit_text(f"❌ Restore failed: {html.escape(str(e))}")
    await status.edit_text("✅ <b>Restored</b>\n" + "\n".join(f"• {k}: {v}" for k, v in counts.items()))
