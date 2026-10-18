import asyncio
import html
import logging
from collections import Counter

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import FloodWait

import database as db
from config import Config
from utils import get_text, index_message_ex, parse_link

admin = filters.user(Config.ADMINS) & filters.private


# ---------- auto indexing ----------
WATCH = filters.channel | filters.group


@Client.on_message(WATCH & (filters.text | filters.caption))
async def auto_index(client, message):
    chat = message.chat
    if not db.is_connected(chat.id):
        if chat.type == ChatType.CHANNEL:
            logging.info("Post seen in NOT connected channel %s - run /connect %s", chat.id, chat.id)
        return
    r, why = await index_message_ex(message)
    if r is None:
        logging.info("Skipped post %s in %s: %s", message.id, chat.id, why)
    else:
        logging.info("Indexed post %s in %s (%s)", message.id, chat.id, "new" if r else "updated")


@Client.on_edited_message(WATCH & (filters.text | filters.caption))
async def auto_update(client, message):
    if db.is_connected(message.chat.id):
        await index_message_ex(message)


@Client.on_deleted_messages(WATCH)
async def auto_delete(client, messages):
    for m in messages:
        if m.chat and db.is_connected(m.chat.id):
            await db.delete_post(db.make_id(m.chat.id, m.id))


# ---------- channel management ----------
@Client.on_message(filters.command("connect") & admin)
async def connect(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /connect <code>-100xxxxxxxxxx</code>")
    try:
        chat_id = int(message.command[1])
        chat = await client.get_chat(chat_id)
        me = await client.get_chat_member(chat_id, "me")
    except Exception as e:
        return await message.reply_text(f"❌ {html.escape(str(e))}")
    if me.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return await message.reply_text("❌ Make the bot an admin of that channel first.")
    await db.add_channel(chat.id, chat.title)
    await message.reply_text(
        f"✅ Connected <b>{html.escape(chat.title)}</b>\n"
        "New posts are indexed automatically. For old posts use /index."
    )


@Client.on_message(filters.command("disconnect") & admin)
async def disconnect(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /disconnect <code>-100id</code> [purge]")
    chat_id = int(message.command[1])
    purge = len(message.command) > 2 and message.command[2].lower() == "purge"
    removed = await db.remove_channel(chat_id, purge)
    await message.reply_text(f"✅ Disconnected." + (f" {removed} posts deleted." if purge else ""))


@Client.on_message(filters.command("channels") & admin)
async def channels(client, message):
    chs = await db.list_channels()
    if not chs:
        return await message.reply_text("No channels connected.")
    lines = []
    for c in chs:
        n = await db.count_posts(c["_id"])
        lines.append(f"• <b>{html.escape(c['title'])}</b> <code>{c['_id']}</code> – {n} posts")
    await message.reply_text("\n".join(lines))


# ---------- bulk indexing of old posts ----------
@Client.on_message(filters.command("index") & admin)
async def index_old(client, message):
    args = message.command[1:]
    if not args:
        return await message.reply_text(
            "Usage: /index <code>-100id [last_msg_id] [first_msg_id]</code>\n"
            "Without last_msg_id the bot finds the newest message itself "
            "(it needs permission to post in the channel).\n"
            "You can also paste a post link as last_msg_id."
        )
    try:
        chat_id = int(args[0])
    except ValueError:
        return await message.reply_text("❌ First argument must be the channel ID like -1001234567890")
    if not db.is_connected(chat_id):
        return await message.reply_text("❌ Connect the channel first with /connect.")
    first = int(args[2]) if len(args) > 2 and args[2].isdigit() else 1

    if len(args) > 1:
        parsed = parse_link(args[1])
        if parsed and parsed[1]:
            last = parsed[1]
        elif args[1].isdigit():
            last = int(args[1])
        else:
            return await message.reply_text("❌ last_msg_id must be a number or a post link.")
    else:
        try:  # find the newest message ID by posting a temporary message
            tmp = await client.send_message(chat_id, ".")
            last = tmp.id - 1
            await tmp.delete()
        except Exception as e:
            return await message.reply_text(
                f"❌ Couldn't detect the last message: {html.escape(str(e))}\n"
                "Long-press your newest post > Copy link, then run:\n"
                "/index <code>-100id &lt;that link&gt;</code>"
            )

    status = await message.reply_text("⏳ Indexing started...")
    new = upd = skipped = 0
    reasons, samples = Counter(), []
    for start in range(first, last + 1, 200):
        ids = list(range(start, min(start + 200, last + 1)))
        while True:
            try:
                msgs = await client.get_messages(chat_id, ids)
                break
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
        for m in msgs:
            if m.empty:
                skipped += 1
                reasons["message empty/deleted"] += 1
                continue
            r, why = await index_message_ex(m)
            if r is True:
                new += 1
            elif r is False:
                upd += 1
            else:
                skipped += 1
                reasons[why] += 1
                if len(samples) < 3 and not why.startswith("no text"):
                    samples.append(get_text(m)[:150])
        try:
            await status.edit_text(
                f"⏳ {min(start + 199, last)}/{last}\n➕ {new} new  ♻️ {upd} updated  ⏭ {skipped} skipped"
            )
        except Exception:
            pass
        await asyncio.sleep(1)
    report = f"✅ Done (scanned IDs {first}–{last}).\n➕ {new} new  ♻️ {upd} updated  ⏭ {skipped} skipped"
    if reasons:
        report += "\n\n<b>Why skipped:</b>\n" + "\n".join(f"• {html.escape(k)}: {v}" for k, v in reasons.items())
    if samples:
        report += "\n\n<b>What I saw in skipped posts:</b>\n" + "\n---\n".join(
            f"<code>{html.escape(s)}</code>" for s in samples
        )
    await status.edit_text(report)
