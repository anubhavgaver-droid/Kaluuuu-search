import asyncio
import html
import time

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, InputUserDeactivated, PeerIdInvalid, UserIsBlocked

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


# ---------------- allowed groups ----------------
@Client.on_message(filters.command("allowgroup") & filters.group & admin_any)
async def allow_group(client, message):
    await db.allow_group(message.chat.id, message.chat.title or "Group")
    await reply_temp(message, "✅ <b>This group is now allowed.</b>\nFrom now on the bot works only in allowed groups.")


@Client.on_message(filters.command("denygroup") & filters.group & admin_any)
async def deny_group(client, message):
    await db.deny_group(message.chat.id)
    await reply_temp(message, "🚫 <b>This group was removed from the allowed list.</b>")


@Client.on_message(filters.command("groups") & admin)
async def groups(client, message):
    await message.reply_text(texts.groups_list(await db.list_groups()))


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
