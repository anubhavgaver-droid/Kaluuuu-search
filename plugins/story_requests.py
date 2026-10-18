import time

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
import search_engine as engine
import texts
from config import Config
from delivery import reply_temp, results_keyboard


@Client.on_message(filters.command("request"))
async def request_cmd(client, message):
    if not message.from_user:
        return
    await db.schedule_delete(message.chat.id, message.id, Config.AUTO_DELETE)
    name = " ".join(message.command[1:]).strip()
    if len(name) < 3:
        return await reply_temp(message, texts.request_usage())

    user = texts.mention(message.from_user)
    group = message.chat.type.name != "PRIVATE"

    # already in the library?
    mode, hits = await engine.search(name)
    if mode == "exact":
        return await reply_temp(message, texts.request_exists(user, name, hits), results_keyboard(hits, group))

    if await db.count_requests(message.from_user.id, time.time() - 86400) >= Config.REQUEST_LIMIT:
        return await reply_temp(message, texts.request_limit(Config.REQUEST_LIMIT))

    where = "Private chat" if not group else (message.chat.title or "Group")
    rid = await db.add_request(message.from_user.id, message.from_user.first_name or "User", name, where)

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Added", callback_data=f"rq:ok:{rid}"),
          InlineKeyboardButton("❌ Reject", callback_data=f"rq:no:{rid}")]]
    )
    targets = [Config.REQUEST_CHAT_ID] if Config.REQUEST_CHAT_ID else Config.ADMINS
    for t in targets:
        try:
            await client.send_message(t, texts.request_admin(name, user, message.from_user.id, where), reply_markup=kb)
        except Exception:
            pass  # admin hasn't started the bot / no access

    await reply_temp(message, texts.request_sent(name))


@Client.on_callback_query(filters.regex(r"^rq:(ok|no):"))
async def request_decision(client, cq):
    if cq.from_user.id not in Config.ADMINS:
        return await cq.answer("Admins only.", show_alert=True)
    _, action, rid = cq.data.split(":")
    r = await db.get_request(rid)
    if not r:
        return await cq.answer("Request not found.", show_alert=True)
    if r["status"] != "pending":
        return await cq.answer(f"Already {r['status']}.", show_alert=True)

    ok = action == "ok"
    await db.set_request_status(rid, "added" if ok else "rejected")

    reachable = True
    try:  # permanent message (not auto-deleted) so the user doesn't miss it
        await client.send_message(r["user_id"], texts.request_done(r["query"], ok))
    except Exception:
        reachable = False

    label = ("✅ <b>Marked as added</b>" if ok else "❌ <b>Rejected</b>") + f" by {texts.mention(cq.from_user)}"
    if not reachable:
        label += "\n⚠️ <i>User couldn't be notified (hasn't started the bot)</i>"
    try:
        await cq.message.edit_text(f"{cq.message.text.html}\n\n{label}", reply_markup=None)
    except Exception:
        pass
    await cq.answer("Done")


@Client.on_message(filters.command("requests") & filters.user(Config.ADMINS) & filters.private)
async def pending(client, message):
    rows = await db.pending_requests(20)
    await message.reply_text(texts.request_list(rows, await db.count_pending()))
