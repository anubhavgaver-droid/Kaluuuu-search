import math
from collections import Counter

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
import guards
import sessions
import texts
from config import Config
from delivery import delete_note, nav_row, reply_temp

PER_PAGE = 15          # story names per page
GENRES_PER_PAGE = 12   # genre buttons per page (2 per row)


def _genres(index) -> list:
    """[(tag, count)] most used first. Genres = the hashtags used on your posts."""
    c = Counter()
    for p in index:
        for t in {x.lower() for x in p["hashtags"]}:
            c[t] += 1
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))


def _nice(tag: str) -> str:
    return tag.lstrip("#").replace("_", " ").title()


def list_view(sid: str, s: dict, page: int):
    """The /filters story list (all stories, or filtered by genre/text)."""
    titles = s["titles"]
    pages = max(1, math.ceil(len(titles) / PER_PAGE))
    page = max(0, min(page, pages - 1))
    chunk = titles[page * PER_PAGE : (page + 1) * PER_PAGE]
    text = texts.library(chunk, page, pages, s["total"], len(titles), s["arg"])

    rows = []
    if pages > 1:
        rows.append(nav_row("lp", sid, page, pages))
    genre_btn = InlineKeyboardButton("🎭 Find by Genre" if not s["arg"] else "🎭 Genres", callback_data=f"lg:{sid}:0")
    if s["arg"]:
        bottom = ([genre_btn] if s["genres"] else []) + [InlineKeyboardButton("📚 Go to all stories", callback_data=f"la:{sid}")]
        rows.append(bottom)
    elif s["genres"]:
        rows.append([genre_btn])
    return text, (InlineKeyboardMarkup(rows) if rows else None)


def genre_view(sid: str, s: dict, page: int):
    """Genre picker: Drama, Romance, ... as buttons."""
    g = s["genres"]
    pages = max(1, math.ceil(len(g) / GENRES_PER_PAGE))
    page = max(0, min(page, pages - 1))
    start = page * GENRES_PER_PAGE

    rows, row = [], []
    for k, (tag, cnt) in enumerate(g[start : start + GENRES_PER_PAGE], start=start):
        row.append(InlineKeyboardButton(f"{_nice(tag)} ({cnt})", callback_data=f"ln:{sid}:{k}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if pages > 1:
        rows.append(nav_row("lg", sid, page, pages))
    rows.append([InlineKeyboardButton("📚 Go to all stories", callback_data=f"la:{sid}")])
    return texts.genre_menu(len(g), page, pages), InlineKeyboardMarkup(rows)


async def _edit(cq, text, kb):
    try:
        await cq.message.edit_text(text + delete_note(), reply_markup=kb, disable_web_page_preview=True)
    except MessageNotModified:
        pass
    await cq.answer()


def _session(cq, parts_len: int):
    parts = cq.data.split(":")
    if len(parts) != parts_len:
        return None, None
    return parts, sessions.get(parts[1])


@Client.on_message(filters.command(["filters", "stories", "list"]))
async def stories(client, message):
    if not message.from_user or guards.group_blocked(message):
        return
    await db.schedule_delete(message.chat.id, message.id, Config.AUTO_DELETE)
    c = guards.cooldown(message.from_user.id, "filters")
    if c != "ok":
        if c == "warn":
            await reply_temp(message, texts.slow_down())
        return
    arg = " ".join(message.command[1:]).strip().lower()
    index = await db.get_index()

    all_titles = sorted({p["title"] for p in index}, key=str.lower)
    items = index
    if arg.startswith("#"):
        items = [p for p in index if any(t.lower() == arg or t.lower().startswith(arg) for t in p["hashtags"])]
    elif arg:
        items = [p for p in index if arg in p["title"].lower()]
    titles = sorted({p["title"] for p in items}, key=str.lower)
    if not titles:
        return await reply_temp(message, texts.library_empty(arg))

    sid = sessions.create(
        {"all": all_titles, "titles": titles, "arg": arg, "total": len(index), "genres": _genres(index)}
    )
    text, kb = list_view(sid, sessions.get(sid), 0)
    await reply_temp(message, text, kb)


# ---- page of the current list ----
@Client.on_callback_query(filters.regex(r"^lp:"))
async def library_page(client, cq):
    parts, s = _session(cq, 3)
    if not parts:
        return await cq.answer()
    if not s:
        return await cq.answer("⌛ Expired. Send /filters again.", show_alert=True)
    text, kb = list_view(parts[1], s, int(parts[2]))
    await _edit(cq, text, kb)


# ---- "Find by Genre": show the genre buttons ----
@Client.on_callback_query(filters.regex(r"^lg:"))
async def library_genres(client, cq):
    parts, s = _session(cq, 3)
    if not parts:
        return await cq.answer()
    if not s:
        return await cq.answer("⌛ Expired. Send /filters again.", show_alert=True)
    if not s["genres"]:
        return await cq.answer("No genres available yet.", show_alert=True)
    text, kb = genre_view(parts[1], s, int(parts[2]))
    await _edit(cq, text, kb)


# ---- a genre was picked: same as /filters #genre ----
@Client.on_callback_query(filters.regex(r"^ln:"))
async def library_pick_genre(client, cq):
    parts, s = _session(cq, 3)
    if not parts:
        return await cq.answer()
    if not s:
        return await cq.answer("⌛ Expired. Send /filters again.", show_alert=True)
    try:
        tag = s["genres"][int(parts[2])][0]
    except (ValueError, IndexError):
        return await cq.answer()
    index = await db.get_index()
    titles = sorted({p["title"] for p in index if any(t.lower() == tag for t in p["hashtags"])}, key=str.lower)
    if not titles:
        return await cq.answer("No stories left in this genre.", show_alert=True)
    s["titles"], s["arg"] = titles, tag
    text, kb = list_view(parts[1], s, 0)
    await _edit(cq, text, kb)


# ---- "Go to all stories": back to the plain /filters reply ----
@Client.on_callback_query(filters.regex(r"^la:"))
async def library_all(client, cq):
    parts, s = _session(cq, 2)
    if not parts:
        return await cq.answer()
    if not s:
        return await cq.answer("⌛ Expired. Send /filters again.", show_alert=True)
    s["titles"], s["arg"] = s["all"], ""
    text, kb = list_view(parts[1], s, 0)
    await _edit(cq, text, kb)
