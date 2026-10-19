from pyrogram import Client, filters

import database as db
from config import Config
import texts
from delivery import deliver, miniapp_button, send_temp
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from utils import parse_start_payload

ADMIN_HELP = (
    "\n\n🛠 <b>Admin commands</b>\n"
    "/connect <code>-100id</code> – connect a channel/group to index (bot must be admin there)\n"
    "/disconnect <code>-100id</code> [purge] – disconnect (purge also deletes its posts)\n"
    "/channels – connected channels\n"
    "/index <code>-100id [last_msg_id] [first_msg_id]</code> – index old posts\n"
    "/add <code>(post text in channel format)</code> – add a post manually\n"
    "/delete <code>name or link</code> – delete a post\n"
    "/parse – reply to a forwarded post to see how I read it\n"
    "/requests – pending story requests\n"
    "/missing – searches that found nothing (<code>/missing clear</code>)\n"
    "/stats – statistics\n"
    "/broadcast – reply to a message (or add text) to send it to all users\n"
    "/ban <code>id [reason]</code> · /unban <code>id</code>\n"
    "/allowgroup · /denygroup (inside a group, or with a group id/@username) · /groups\n"
    "/backup – send a database backup · /restore – reply to a backup file"
)


@Client.on_message(filters.command(["start", "help"]) & filters.private)
async def start(client, message):
    await db.add_user(message.from_user.id)

    # deep link from a group: t.me/<bot>?start=q<post id>_<owner id>
    if len(message.command) > 1:
        parsed = parse_start_payload(message.command[1])
        if parsed:
            pid, owner = parsed
            await db.schedule_delete(message.chat.id, message.id, Config.AUTO_DELETE)
            if owner and owner != message.from_user.id:
                # someone else's search result -> send them back to search their own
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Search your own story", url=Config.GROUP_LINK)]])
                return await send_temp(client, message.from_user.id, texts.not_your_search(), kb)
            return await deliver(client, message.from_user.id, pid)

    if len(message.command) > 1 and message.command[1] == "app":  # from the group's Mini App button
        btn = miniapp_button(True)
        if btn:
            return await send_temp(client, message.from_user.id, texts.miniapp_card(), InlineKeyboardMarkup([[btn]]))

    text = texts.welcome()
    if message.from_user.id in Config.ADMINS:
        text += ADMIN_HELP
    btn = miniapp_button(True)
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup([[btn]]) if btn else None)
