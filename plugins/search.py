import time

from pyrogram import Client, filters

import database as db
import search_engine as engine
import texts
from config import Config
from delivery import deliver, reply_temp, results_keyboard, results_text


# ---- private chat search ----
@Client.on_message(filters.private & filters.text & ~filters.regex(r"^/"))
async def on_pm_query(client, message):
    q = message.text.strip()
    await db.schedule_delete(message.chat.id, message.id, Config.AUTO_DELETE)
    if len(q) < 2:
        return await reply_temp(message, texts.too_short())
    user = texts.mention(message.from_user)
    t0 = time.perf_counter()
    mode, hits = await engine.search(q)
    elapsed = time.perf_counter() - t0
    if not hits:
        return await reply_temp(message, texts.not_found(user, q, elapsed))
    await reply_temp(
        message,
        texts.results(mode, hits, user, q, elapsed),
        results_keyboard(hits, group=False),
    )


# ---- group search (group=1 so it never competes with the indexing handlers) ----
@Client.on_message(filters.group & filters.text & ~filters.regex(r"^/") & ~filters.bot, group=1)
async def on_group_query(client, message):
    if not message.from_user or db.is_connected(message.chat.id):
        return
    q = message.text.strip()
    if not (3 <= len(q) <= 80):
        return
    t0 = time.perf_counter()
    mode, hits = await engine.search(q, Config.GROUP_MIN_SCORE)
    elapsed = time.perf_counter() - t0
    if not hits:
        return  # stay quiet in groups when nothing matches
    await reply_temp(
        message,
        texts.results(mode, hits, texts.mention(message.from_user), q, elapsed),
        results_keyboard(hits, group=True),
    )
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
