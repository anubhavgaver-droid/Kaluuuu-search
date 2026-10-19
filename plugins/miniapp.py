from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardMarkup

import database as db
import texts
from config import Config
from delivery import miniapp_button, reply_temp


@Client.on_message(filters.command(["app", "miniapp"]))
async def open_app(client, message):
    await db.schedule_delete(message.chat.id, message.id, Config.AUTO_DELETE)
    btn = miniapp_button(message.chat.type == ChatType.PRIVATE)
    if not btn:
        return await reply_temp(message, "⚠️ Mini App isn't configured yet (BASE_URL missing).")
    await reply_temp(message, texts.miniapp_card(), InlineKeyboardMarkup([[btn]]))
