import html
from datetime import datetime, timedelta

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
import search_engine as engine
from utils import post_link


def card(p: dict) -> str:
    tags = html.escape(" ".join(p["hashtags"][:8]))
    kind = "🔒 Private" if p["is_private"] else "🌐 Public"
    return f"<b>{html.escape(p['title'])}</b>\n{tags}\n{kind}".replace("\n\n", "\n")


def keyboard(hits: list) -> InlineKeyboardMarkup:
    rows = []
    for p in hits:
        label = f"{'🔒' if p['is_private'] else '🌐'} {p['title'][:40]}"
        if p["is_private"]:
            rows.append([InlineKeyboardButton(label, callback_data=f"o:{p['_id']}")])
        else:
            rows.append([InlineKeyboardButton(label, url=post_link(p))])
    return InlineKeyboardMarkup(rows)


@Client.on_message(filters.private & filters.text & ~filters.regex(r"^/"))
async def on_query(client, message):
    q = message.text.strip()
    if len(q) < 2:
        return await message.reply_text("✍️ Please type at least 2 characters.")
    mode, hits = await engine.search(q)
    if not hits:
        return await message.reply_text("❌ Nothing found. Check the spelling or try another name.")
    header = {
        "exact": "🔎 <b>Result</b>",
        "tag": "🏷 <b>Posts with this hashtag</b>",
        "suggest": "🤔 <b>Did you mean one of these?</b>",
    }[mode]
    body = "\n\n".join(card(p) for p in hits)
    await message.reply_text(
        f"{header}\n\n{body}", reply_markup=keyboard(hits), disable_web_page_preview=True
    )


@Client.on_callback_query(filters.regex(r"^o:"))
async def open_post(client, cq):
    pid = cq.data[2:]
    p = await db.get_post(pid)
    if not p:
        return await cq.answer("⚠️ This post was removed.", show_alert=True)

    link = post_link(p)
    if not p["is_private"]:
        await cq.answer()
        return await cq.message.reply_text(
            "✅ Here you go:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📂 Open post", url=link)]]),
        )

    # private channel: is the user a member?
    try:
        m = await client.get_chat_member(p["target_chat_id"], cq.from_user.id)
        joined = m.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
    except UserNotParticipant:
        joined = False
    except Exception:
        return await cq.answer("⚠️ Bot can't check this channel right now (is it admin there?).", show_alert=True)

    if joined:
        await cq.answer()
        return await cq.message.reply_text(
            "✅ You're already a member. Here's your post:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📂 Open post", url=link)]]),
        )

    try:
        invite = await client.create_chat_invite_link(
            p["target_chat_id"],
            name=f"u{cq.from_user.id}",
            expire_date=datetime.now() + timedelta(minutes=10),
            member_limit=1,
        )
    except Exception:
        return await cq.answer("⚠️ Couldn't create a join link. Contact the admin.", show_alert=True)

    await cq.answer()
    await cq.message.reply_text(
        "🔒 This post is in a private channel.\nJoin first, then tap <b>I've joined</b>.",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ Join channel", url=invite.invite_link)],
                [InlineKeyboardButton("✅ I've joined – get post", callback_data=f"o:{pid}")],
            ]
        ),
    )
