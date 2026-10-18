import asyncio
import html

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait

import database as db
from config import Config
from utils import index_message

admin = filters.user(Config.ADMINS) & filters.private


# ---------- auto indexing ----------
@Client.on_message(filters.channel & (filters.text | filters.caption))
async def auto_index(client, message):
    if db.is_connected(message.chat.id):
        await index_message(message)


@Client.on_edited_message(filters.channel & (filters.text | filters.caption))
async def auto_update(client, message):
    if db.is_connected(message.chat.id):
        await index_message(message)


@Client.on_deleted_messages(filters.channel)
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
    if len(args) < 2:
        return await message.reply_text(
            "Usage: /index <code>-100id last_msg_id [first_msg_id]</code>\n"
            "last_msg_id = ID of the newest post in the channel."
        )
    chat_id, last = int(args[0]), int(args[1])
    first = int(args[2]) if len(args) > 2 else 1
    if not db.is_connected(chat_id):
        return await message.reply_text("❌ Connect the channel first with /connect.")

    status = await message.reply_text("⏳ Indexing started...")
    new = upd = skipped = 0
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
                continue
            r = await index_message(m)
            if r is True:
                new += 1
            elif r is False:
                upd += 1
            else:
                skipped += 1
        try:
            await status.edit_text(
                f"⏳ {min(start + 199, last)}/{last}\n➕ {new} new  ♻️ {upd} updated  ⏭ {skipped} skipped"
            )
        except Exception:
            pass
        await asyncio.sleep(1)
    await status.edit_text(f"✅ Done.\n➕ {new} new  ♻️ {upd} updated  ⏭ {skipped} skipped")
