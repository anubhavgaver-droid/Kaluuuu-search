# Auto Post Search Bot (Pyrogram + MongoDB + RapidFuzz)

## Post format (in your index channel)
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
