from pyrogram import Client, filters

import database as db
from config import Config
from delivery import deliver

USER_HELP = (
    "👋 <b>Welcome!</b>\n\n"
    "Send me the name of a story/post and I'll find it for you.\n"
    "Spelling mistakes are fine. You can also search by hashtag, e.g. <code>#romance</code>.\n"
    "You can search in groups too - I'll reply there with your post."
)

ADMIN_HELP = (
    "\n\n🛠 <b>Admin commands</b>\n"
    "/connect <code>-100id</code> – connect a channel/group to index (bot must be admin there)\n"
    "/disconnect <code>-100id</code> [purge] – disconnect (purge also deletes its posts)\n"
    "/channels – connected channels\n"
    "/index <code>-100id [last_msg_id] [first_msg_id]</code> – index old posts\n"
    "/add <code>(post text in channel format)</code> – add a post manually\n"
    "/delete <code>name or link</code> – delete a post\n"
    "/parse – reply to a forwarded post to see how I read it\n"
    "/stats – statistics"
)


@Client.on_message(filters.command(["start", "help"]) & filters.private)
async def start(client, message):
    await db.add_user(message.from_user.id)

    # deep link from a group: t.me/<bot>?start=p<post id>
    if len(message.command) > 1 and message.command[1].startswith("p"):
        await db.schedule_delete(message.chat.id, message.id, Config.AUTO_DELETE)
        return await deliver(client, message.from_user.id, message.command[1][1:])

    text = USER_HELP
    if message.from_user.id in Config.ADMINS:
        text += ADMIN_HELP
    await message.reply_text(text)
