# Auto Post Search Bot (Pyrogram + MongoDB + RapidFuzz)

## Post format (in your index channel or group)
The post number in the link is optional: `https://t.me/channelname` also works.

Private story:
```
Story Name
https://t.me/c/1234567890/45
-1001234567890
#romance #hindi
#Private
```
Public story:
```
Story Name
https://t.me/channelname/45
#romance #hindi
#Public
```
The bot indexes the channel where you post these. For private stories the bot must be
admin in that story's channel (to check membership and make join links).

## Local run
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`, fill it in
3. `python bot.py`

## Render
- New > Web Service, connect the repo (or use render.yaml)
- Build: `pip install -r requirements.txt`   Start: `python bot.py`
- Env vars: API_ID, API_HASH, BOT_TOKEN, MONGO_URI, ADMINS, PYTHON_VERSION=3.11.9
- Render provides PORT; the bot serves / and /health on it.
- MongoDB Atlas: allow Render's IP (0.0.0.0/0 on free tier).

## Admin
/connect -100id (index channel), /index -100id last_msg_id, /add, /delete, /channels, /stats

## Groups & auto-delete
- Add the bot to your search group. In @BotFather: /setprivacy -> Disable (or make the bot admin) so it can read messages.
- Give it "Delete messages" right if you want users' search messages removed too.
- In a group the bot replies "Here is your post" with buttons. Each button opens the bot's PM through a
  start-parameter deep link (t.me/<bot>?start=p<id>), where private stories ask the user to join first.
- Everything (search results, links, join prompts, users' queries) auto-deletes after AUTO_DELETE_SECONDS (default 300).
  Admin command replies are not deleted.
- In groups the bot only answers strong matches (GROUP_MIN_SCORE, default 75) and stays silent otherwise.
