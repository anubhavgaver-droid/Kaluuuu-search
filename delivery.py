from datetime import datetime, timedelta

from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import database as db
import texts
from config import Config
from utils import make_start_payload, post_link


def delete_note() -> str:
    if Config.AUTO_DELETE <= 0:
        return ""
    return f"\n⏳ <i>Auto-deletes in {max(1, Config.AUTO_DELETE // 60)} min</i>"


def deep_link(pid: str, owner_id=None) -> str:
    return f"https://t.me/{Config.BOT_USERNAME}?start={make_start_payload(pid, owner_id)}"


def results_text(mode, hits, user_html, query, elapsed) -> str:
    return texts.results(mode, hits, user_html, query, elapsed) + delete_note()


def nav_row(prefix: str, sid: str, page: int, pages: int) -> list:
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️ Back", callback_data=f"{prefix}:{sid}:{page - 1}"))
    row.append(InlineKeyboardButton(f"📄 {page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        row.append(InlineKeyboardButton("Next ➡️", callback_data=f"{prefix}:{sid}:{page + 1}"))
    return row


def results_keyboard(hits: list, group: bool, sid=None, page: int = 0, pages: int = 1, owner_id=None) -> InlineKeyboardMarkup:
    rows = []
    for p in hits:
        label = f"{'🔒' if p['is_private'] else '📖'} {p['title'][:42]}"
        if group:  # groups: always go through the bot's PM (deep link)
            rows.append([InlineKeyboardButton(label, url=deep_link(p["_id"], owner_id))])
        elif p["is_private"]:
            rows.append([InlineKeyboardButton(label, callback_data=f"o:{p['_id']}")])
        else:
            rows.append([InlineKeyboardButton(label, url=post_link(p))])
    if sid and pages > 1:
        rows.append(nav_row("pg", sid, page, pages))
    return InlineKeyboardMarkup(rows)


async def reply_temp(message, text, kb=None):
    """Reply and schedule the reply for auto-delete."""
    sent = await message.reply_text(text + delete_note(), reply_markup=kb, disable_web_page_preview=True)
    await db.schedule_delete(sent.chat.id, sent.id, Config.AUTO_DELETE)
    return sent


async def send_temp(client, chat_id, text, kb=None):
    sent = await client.send_message(
        chat_id, text + delete_note(), reply_markup=kb, disable_web_page_preview=True
    )
    await db.schedule_delete(chat_id, sent.id, Config.AUTO_DELETE)
    return sent


async def deliver(client, user_id: int, pid: str):
    """Send the user (in PM) the link, after checking/joining for private channels."""
    p = await db.get_post(pid)
    if not p:
        return await send_temp(client, user_id, texts.removed())

    open_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📂 Open post", url=post_link(p))]])

    if not p["is_private"]:
        return await send_temp(client, user_id, texts.link_ready(p["title"]), open_kb)

    # private channel: is the user a member?
    try:
        m = await client.get_chat_member(p["target_chat_id"], user_id)
        joined = m.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
    except UserNotParticipant:
        joined = False
    except Exception:
        return await send_temp(client, user_id, texts.cant_check())

    if joined:
        return await send_temp(client, user_id, texts.link_ready(p["title"]), open_kb)

    try:
        invite = await client.create_chat_invite_link(
            p["target_chat_id"],
            name=f"u{user_id}",
            expire_date=datetime.now() + timedelta(minutes=10),
            member_limit=1,
        )
    except Exception:
        return await send_temp(client, user_id, texts.cant_invite())

    return await send_temp(
        client,
        user_id,
        texts.join_required(p["title"]),
        InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Join channel", url=invite.invite_link)],
                [InlineKeyboardButton("✅ I've joined", callback_data=f"j:{pid}")],
            ]
        ),
    )


def miniapp_button(private: bool):
    """Open-Mini-App button. In PM it opens the app directly; in groups it must be a link."""
    if not Config.WEBAPP_URL:
        return None
    if private:
        return InlineKeyboardButton("🚀 Open Mini App", web_app=WebAppInfo(url=Config.WEBAPP_URL))
    return InlineKeyboardButton("🚀 Open Mini App", url=Config.MINIAPP_LINK or f"https://t.me/{Config.BOT_USERNAME}?start=app")
