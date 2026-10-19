from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
import texts
from config import Config
from delivery import deliver
from notifier import admin_targets
from utils import post_link


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
          InlineKeyboardButton("✅ Ignore", callback_data=f"rpi:{pid}")]]
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
