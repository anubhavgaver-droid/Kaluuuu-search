import html
from datetime import datetime, timedelta

from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from config import Config
from utils import post_link


def delete_note() -> str:
    if Config.AUTO_DELETE <= 0:
        return ""
    return f"\n\n⏳ <i>Auto-deletes in {max(1, Config.AUTO_DELETE // 60)} min</i>"


def card(p: dict) -> str:
    tags = html.escape(" ".join(p["hashtags"][:8]))
    kind = "🔒 Private" if p["is_private"] else "🌐 Public"
    lines = [f"<b>{html.escape(p['title'])}</b>"]
    if tags:
        lines.append(tags)
    lines.append(kind)
    return "\n".join(lines)


def deep_link(pid: str) -> str:
    return f"https://t.me/{Config.BOT_USERNAME}?start=p{pid}"


def results_text(mode: str, hits: list) -> str:
    header = {
        "exact": "🔎 <b>Here is your post 👇</b>",
        "tag": "🏷 <b>Posts with this hashtag 👇</b>",
        "suggest": "🤔 <b>Did you mean one of these? 👇</b>",
    }[mode]
    return header + "\n\n" + "\n\n".join(card(p) for p in hits) + delete_note()


def results_keyboard(hits: list, group: bool) -> InlineKeyboardMarkup:
    rows = []
    for p in hits:
        label = f"{'🔒' if p['is_private'] else '🌐'} {p['title'][:40]}"
        if group:  # groups: always go through the bot's PM (deep link)
            rows.append([InlineKeyboardButton(label, url=deep_link(p["_id"]))])
        elif p["is_private"]:
            rows.append([InlineKeyboardButton(label, callback_data=f"o:{p['_id']}")])
        else:
            rows.append([InlineKeyboardButton(label, url=post_link(p))])
    return InlineKeyboardMarkup(rows)


async def reply_temp(message, text, kb=None):
    """Reply and schedule the reply for auto-delete."""
    sent = await message.reply_text(text, reply_markup=kb, disable_web_page_preview=True)
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
        return await send_temp(client, user_id, "⚠️ This post was removed.")

    title = html.escape(p["title"])
    open_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📂 Open post", url=post_link(p))]])

    if not p["is_private"]:
        return await send_temp(client, user_id, f"✅ <b>Here is your link</b>\n{title}", open_kb)

    # private channel: is the user a member?
    try:
        m = await client.get_chat_member(p["target_chat_id"], user_id)
        joined = m.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
    except UserNotParticipant:
        joined = False
    except Exception:
        return await send_temp(
            client, user_id, "⚠️ I can't check that channel right now. Please tell the admin (bot must be admin there)."
        )

    if joined:
        return await send_temp(client, user_id, f"✅ <b>Here is your link</b>\n{title}", open_kb)

    try:
        invite = await client.create_chat_invite_link(
            p["target_chat_id"],
            name=f"u{user_id}",
            expire_date=datetime.now() + timedelta(minutes=10),
            member_limit=1,
        )
    except Exception:
        return await send_temp(client, user_id, "⚠️ Couldn't create a join link. Please contact the admin.")

    return await send_temp(
        client,
        user_id,
        f"🔒 <b>{title}</b>\n\nFirst you need to join this channel, because the post is uploaded there.\n"
        "After joining, tap <b>I've joined</b>.",
        InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Join channel", url=invite.invite_link)],
                [InlineKeyboardButton("✅ I've joined", callback_data=f"j:{pid}")],
            ]
        ),
    )
