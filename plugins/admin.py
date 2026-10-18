import html

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
import search_engine as engine
from config import Config
from utils import diagnose, get_text, manual_id, parse_link, parse_post, post_link

admin = filters.user(Config.ADMINS) & filters.private


@Client.on_message(filters.command("add") & admin)
async def add(client, message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        return await message.reply_text(
            "Usage: send /add and then the post in channel format:\n\n"
            "<code>/add Story Name\n"
            "https://t.me/c/1234567890/45\n"
            "-1001234567890\n"
            "#romance #hindi\n"
            "#Private</code>"
        )
    data = parse_post(parts[1])
    if not data or not data["title"]:
        return await message.reply_text(
            "❌ Couldn't read that. Need a story name and a t.me link (post number optional). "
            "Private stories also need the channel ID, e.g. -1001234567890."
        )
    await db.add_post(manual_id(data), data)
    kind = "🔒 Private" if data["is_private"] else "🌐 Public"
    await message.reply_text(f"✅ Added: <b>{html.escape(data['title'])}</b> ({kind})")


@Client.on_message(filters.command("delete") & admin)
async def delete(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /delete <code>story name or post link</code>")
    arg = message.text.split(None, 1)[1].strip()

    parsed = parse_link(arg)
    if parsed:
        p = await db.find_by_link(*parsed)
        if not p:
            return await message.reply_text("❌ That post isn't in the database.")
        await db.delete_post(p["_id"])
        return await message.reply_text(f"🗑 Deleted: <b>{html.escape(p['title'])}</b>")

    res = await engine.fuzzy(arg, 5, 50)
    if not res:
        return await message.reply_text("❌ No matching post.")
    rows = [[InlineKeyboardButton(f"🗑 {p['title'][:45]}", callback_data=f"d:{p['_id']}")] for p, _ in res]
    await message.reply_text("Which one to delete?", reply_markup=InlineKeyboardMarkup(rows))


@Client.on_callback_query(filters.regex(r"^d:"))
async def delete_cb(client, cq):
    if cq.from_user.id not in Config.ADMINS:
        return await cq.answer("Admins only.", show_alert=True)
    ok = await db.delete_post(cq.data[2:])
    await cq.answer("🗑 Deleted" if ok else "Already deleted", show_alert=False)
    await cq.message.edit_text("🗑 Post deleted." if ok else "Already deleted.")


@Client.on_message(filters.command("stats") & admin)
async def stats(client, message):
    await message.reply_text(
        f"📊 <b>Stats</b>\n"
        f"Posts: {await db.count_posts()}\n"
        f"Channels: {len(await db.list_channels())}\n"
        f"Users: {await db.count_users()}"
    )


@Client.on_message(filters.command("parse") & admin)
async def parse_cmd(client, message):
    src = message.reply_to_message
    if not src:
        return await message.reply_text(
            "Forward a post from your channel to me, then reply to it with /parse.\n"
            "I'll show exactly how I read it."
        )
    text = get_text(src)
    seen = html.escape(text[:400]) or "(empty)"
    data = parse_post(text) if text.strip() else None
    if not data or not data["title"]:
        return await message.reply_text(
            f"❌ Skipped: <b>{html.escape(diagnose(text))}</b>\n\nI see this text:\n<code>{seen}</code>"
        )
    await message.reply_text(
        "✅ Readable\n"
        f"Title: <b>{html.escape(data['title'])}</b>\n"
        f"Tags: {html.escape(' '.join(data['hashtags']) or '-')}\n"
        f"Type: {'🔒 Private' if data['is_private'] else '🌐 Public'}\n"
        f"Link: {html.escape(post_link(data))}",
        disable_web_page_preview=True,
    )
