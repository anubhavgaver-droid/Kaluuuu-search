import asyncio
import math
import time

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified

import database as db
import search_engine as engine
import sessions
import texts
from config import Config
from delivery import deliver, delete_note, reply_temp, results_keyboard

# normal chat words the bot should never answer in a group
GROUP_IGNORE = {
    "hello", "hii", "hiii", "hey", "heyy", "thanks", "thank you", "thankyou", "okay", "yes", "yeah",
    "good morning", "good night", "good evening", "welcome", "bye", "lol", "haha", "nice", "wow",
}


async def ai_thinking(message):
    """'AI Search' effect (~2s): progress bar animates through a few frames, then the message is deleted."""
    m = None
    try:
        m = await message.reply_text(texts.ai_frame(0))
        for i in range(1, texts.AI_FRAME_COUNT):
            await asyncio.sleep(0.5)
            await m.edit_text(texts.ai_frame(i))
        await asyncio.sleep(0.5)
    except Exception:
        pass
    finally:
        if m:
            try:
                await m.delete()
            except Exception:
                pass


async def respond(message, q: str, group: bool) -> bool:
    user = texts.mention(message.from_user)

    t0 = time.perf_counter()
    mode, hits = await engine.search(q, Config.GROUP_MIN_SCORE if group else None)
    if mode == "none" and not group and not q.startswith("#"):
        mode, hits = await engine.search(q, relaxed=True)  # last-chance AI pass
    elapsed = time.perf_counter() - t0

    if not hits:
        if group:
            return False  # stay quiet in groups when nothing matches
        await reply_temp(message, texts.not_found(user, q, elapsed))
        return True

    sid, page_info, pages, view = None, None, 1, hits
    if mode in ("suggest", "tag") and len(hits) > Config.PAGE_SIZE:
        pages = math.ceil(len(hits) / Config.PAGE_SIZE)
        sid = sessions.create(
            {"mode": mode, "query": q, "hits": hits, "user_id": message.from_user.id,
             "user_html": user, "elapsed": elapsed, "group": group}
        )
        view = hits[: Config.PAGE_SIZE]
        page_info = (1, pages, len(hits))

    if mode == "suggest":
        await ai_thinking(message)  # "AI Search" shows, vanishes, then "Did you mean"

    await reply_temp(
        message,
        texts.results(mode, view, user, q, elapsed, page_info),
        results_keyboard(view, group, sid, 0, pages),
    )
    return True


# ---- private chat search ----
@Client.on_message(filters.private & filters.text & ~filters.regex(r"^/"))
async def on_pm_query(client, message):
    q = message.text.strip()
    await db.schedule_delete(message.chat.id, message.id, Config.AUTO_DELETE)
    if len(q) < 2:
        return await reply_temp(message, texts.too_short())
    await respond(message, q, group=False)


# ---- group search (group=1 so it never competes with the indexing handlers) ----
@Client.on_message(filters.group & filters.text & ~filters.regex(r"^/") & ~filters.bot, group=1)
async def on_group_query(client, message):
    if not message.from_user or db.is_connected(message.chat.id):
        return
    q = message.text.strip()
    if not (4 <= len(q) <= 80) or q.lower() in GROUP_IGNORE:
        return
    if await respond(message, q, group=True):
        await db.schedule_delete(message.chat.id, message.id, Config.AUTO_DELETE)  # needs delete right


# ---- pagination (Back / Next) ----
@Client.on_callback_query(filters.regex(r"^pg:"))
async def paginate(client, cq):
    try:
        _, sid, page = cq.data.split(":")
        page = int(page)
    except ValueError:
        return await cq.answer()
    s = sessions.get(sid)
    if not s:
        return await cq.answer("⌛ This search expired. Please search again.", show_alert=True)
    if cq.from_user.id != s["user_id"]:
        return await cq.answer("This is someone else's search 🙂 Send your own search!", show_alert=True)

    ps = Config.PAGE_SIZE
    pages = math.ceil(len(s["hits"]) / ps)
    page = max(0, min(page, pages - 1))
    view = s["hits"][page * ps : (page + 1) * ps]
    text = texts.results(s["mode"], view, s["user_html"], s["query"], s["elapsed"], (page + 1, pages, len(s["hits"])))
    try:
        await cq.message.edit_text(
            text + delete_note(),
            reply_markup=results_keyboard(view, s["group"], sid, page, pages),
            disable_web_page_preview=True,
        )
    except MessageNotModified:
        pass
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^noop$"))
async def noop(client, cq):
    await cq.answer()


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
