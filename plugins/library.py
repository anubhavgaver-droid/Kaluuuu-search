import math

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardMarkup

import database as db
import sessions
import texts
from config import Config
from delivery import delete_note, nav_row, reply_temp

PER_PAGE = 15


def render(sid: str, s: dict, page: int):
    pages = max(1, math.ceil(len(s["titles"]) / PER_PAGE))
    page = max(0, min(page, pages - 1))
    chunk = s["titles"][page * PER_PAGE : (page + 1) * PER_PAGE]
    text = texts.library(chunk, page, pages, s["total"], len(s["titles"]), s["arg"])
    kb = InlineKeyboardMarkup([nav_row("lp", sid, page, pages)]) if pages > 1 else None
    return text, kb


@Client.on_message(filters.command(["filters", "stories", "list"]))
async def stories(client, message):
    if not message.from_user:
        return
    await db.schedule_delete(message.chat.id, message.id, Config.AUTO_DELETE)
    arg = " ".join(message.command[1:]).strip().lower()
    index = await db.get_index()

    items = index
    if arg.startswith("#"):
        items = [p for p in index if any(t.lower() == arg or t.lower().startswith(arg) for t in p["hashtags"])]
    elif arg:
        items = [p for p in index if arg in p["title"].lower()]

    titles = sorted({p["title"] for p in items}, key=str.lower)
    if not titles:
        return await reply_temp(message, texts.library_empty(arg))

    sid = sessions.create({"titles": titles, "arg": arg, "total": len(index)})
    text, kb = render(sid, sessions.get(sid), 0)
    await reply_temp(message, text, kb)


@Client.on_callback_query(filters.regex(r"^lp:"))
async def library_page(client, cq):
    try:
        _, sid, page = cq.data.split(":")
        page = int(page)
    except ValueError:
        return await cq.answer()
    s = sessions.get(sid)
    if not s:
        return await cq.answer("⌛ Expired. Send /filters again.", show_alert=True)
    text, kb = render(sid, s, page)
    try:
        await cq.message.edit_text(text + delete_note(), reply_markup=kb, disable_web_page_preview=True)
    except MessageNotModified:
        pass
    await cq.answer()
