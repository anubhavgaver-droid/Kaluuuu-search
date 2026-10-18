from pyrogram import Client, filters

import database as db
import search_engine as engine
from config import Config
from delivery import deliver, reply_temp, results_keyboard, results_text


# ---- private chat search ----
@Client.on_message(filters.private & filters.text & ~filters.regex(r"^/"))
async def on_pm_query(client, message):
    q = message.text.strip()
    await db.schedule_delete(message.chat.id, message.id, Config.AUTO_DELETE)
    if len(q) < 2:
        return await reply_temp(message, "✍️ Please type at least 2 characters.")
    mode, hits = await engine.search(q)
    if not hits:
        return await reply_temp(message, "❌ Nothing found. Check the spelling or try another name.")
    await reply_temp(message, results_text(mode, hits), results_keyboard(hits, group=False))


# ---- group search (group=1 so it never competes with the indexing handlers) ----
@Client.on_message(filters.group & filters.text & ~filters.regex(r"^/") & ~filters.bot, group=1)
async def on_group_query(client, message):
    if not message.from_user or db.is_connected(message.chat.id):
        return
    q = message.text.strip()
    if not (3 <= len(q) <= 80):
        return
    mode, hits = await engine.search(q, Config.GROUP_MIN_SCORE)
    if not hits:
        return  # stay quiet in groups when nothing matches
    await reply_temp(message, results_text(mode, hits), results_keyboard(hits, group=True))
    await db.schedule_delete(message.chat.id, message.id, Config.AUTO_DELETE)  # needs delete right


# ---- private result button (private channel) ----
@Client.on_callback_query(filters.regex(r"^o:"))
async def open_post(client, cq):
    await cq.answer()
    await deliver(client, cq.from_user.id, cq.data[2:])


# ---- "I've joined" ----
@Client.on_callback_query(filters.regex(r"^j:"))
async def joined(client, cq):
    await cq.answer()
    await deliver(client, cq.from_user.id, cq.data[2:])
    try:
        await cq.message.delete()  # remove the old join prompt
    except Exception:
        pass
