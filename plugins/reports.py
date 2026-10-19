import re

from pyrogram import Client, filters
from pyrogram.types import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup

import database as db
import texts
from config import Config
from delivery import deliver
from notifier import admin_targets
from utils import parse_post, post_link


@Client.on_callback_query(filters.regex(r"^rp:"))
async def report(client, cq):
    pid = cq.data[3:]
    p = await db.get_post(pid)
    if not p:
        return await cq.answer("This story was already removed. Thanks!", show_alert=True)
    if not await db.add_report(pid, cq.from_user.id):
        return await cq.answer("You already reported this one. Thank you! 🙏", show_alert=True)

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🗑 Delete story", callback_data=f"rpd:{pid}"),
          InlineKeyboardButton("✅ Ignore", callback_data=f"rpi:{pid}")],
         [InlineKeyboardButton("🔗 Add new link", callback_data=f"rpl:{pid}")]]
    )
    text = texts.report_admin(p["title"], post_link(p), texts.mention(cq.from_user))
    for t in admin_targets():
        try:
            await client.send_message(t, text, reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            pass
    await cq.answer("Thanks! The admin has been notified. 🙏", show_alert=True)


async def _finish(cq, label: str):
    try:
        await cq.message.edit_text(f"{cq.message.text.html}\n\n{label} by {texts.mention(cq.from_user)}", reply_markup=None, disable_web_page_preview=True)
    except Exception:
        pass


@Client.on_callback_query(filters.regex(r"^rpd:"))
async def report_delete(client, cq):
    if cq.from_user.id not in Config.ADMINS:
        return await cq.answer("Admins only.", show_alert=True)
    ok = await db.delete_post(cq.data[4:])
    await _finish(cq, "🗑 <b>Story deleted</b>" if ok else "ℹ️ <b>Already deleted</b>")
    await cq.answer("Deleted" if ok else "Already deleted")


@Client.on_callback_query(filters.regex(r"^rpi:"))
async def report_ignore(client, cq):
    if cq.from_user.id not in Config.ADMINS:
        return await cq.answer("Admins only.", show_alert=True)
    await _finish(cq, "✅ <b>Ignored</b>")
    await cq.answer("Ignored")


# ---- "I've joined" for the force-subscribe channel ----
@Client.on_callback_query(filters.regex(r"^fs:"))
async def force_sub_retry(client, cq):
    await cq.answer()
    await deliver(client, cq.from_user.id, cq.data[3:])
    try:
        await cq.message.delete()
    except Exception:
        pass


# ---- "Add new link": admin replies to a prompt with the corrected link ----
MARK = "SET NEW LINK"


@Client.on_callback_query(filters.regex(r"^rpl:"))
async def report_new_link(client, cq):
    if cq.from_user.id not in Config.ADMINS:
        return await cq.answer("Admins only.", show_alert=True)
    pid = cq.data[4:]
    p = await db.get_post(pid)
    if not p:
        return await cq.answer("This story no longer exists.", show_alert=True)
    await cq.answer()
    await client.send_message(
        cq.message.chat.id,
        texts.set_link_prompt(p["title"], pid, f"{cq.message.chat.id}:{cq.message.id}", texts.mention(cq.from_user)),
        reply_markup=ForceReply(selective=True, placeholder="https://t.me/channel/45"),
        disable_web_page_preview=True,
    )


async def _is_link_reply(_, __, m):
    rep = m.reply_to_message
    return bool(
        m.from_user and m.from_user.id in Config.ADMINS
        and rep and rep.from_user and rep.from_user.is_bot and rep.text and MARK in rep.text
    )


link_reply = filters.create(_is_link_reply)


# group=-5 runs before the normal search handler, which would otherwise treat this reply as a search
@Client.on_message(filters.text & link_reply, group=-5)
async def apply_new_link(client, message):
    rep = message.reply_to_message
    m = re.search(r"ID:\s*(\S+)", rep.text)
    p = await db.get_post(m.group(1)) if m else None
    if not p:
        await message.reply_text("❌ That story no longer exists.")
        message.stop_propagation()

    data = parse_post(f"{p['title']}\n{message.text}")  # title + the new link / channel id / #private
    if not data:
        await message.reply_text("❌ I couldn't read that. Reply again with a t.me link (private: also the -100… channel ID).")
        message.stop_propagation()

    fields = {k: data[k] for k in ("is_private", "target_chat_id", "target_username", "target_msg_id", "invite_url")}
    await db.update_post_fields(p["_id"], fields)
    new_link = post_link({**p, **fields})
    await message.reply_text(
        texts.link_changed(p["title"], new_link, fields["is_private"]),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📂 Test the new link", url=new_link)]]),
        disable_web_page_preview=True,
    )

    ref = re.search(r"Ref:\s*(-?\d+):(\d+)", rep.text)  # mark the original report as handled
    if ref:
        try:
            chat_id, mid = int(ref.group(1)), int(ref.group(2))
            orig = await client.get_messages(chat_id, mid)
            await client.edit_message_text(
                chat_id, mid,
                f"{orig.text.html}\n\n🔗 <b>Link changed</b> by {texts.mention(message.from_user)}",
                reply_markup=None, disable_web_page_preview=True,
            )
        except Exception:
            pass
    message.stop_propagation()
