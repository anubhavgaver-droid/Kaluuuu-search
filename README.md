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

## Mini App
- Served by the same server: `https://<your-render-url>/app` (API under `/api/*`, checked with Telegram's signed initData).
- Open it: /app command, the button under /start, or the bot's menu button (set automatically).
- Search / genre chips / "Get link" -> deep link to the bot chat (same flow as the group results).
- In groups the button is a link; for a clean in-group button create the app in @BotFather (/newapp) and set MINIAPP_LINK.

## More features
- **/missing** (admin): searches that found nothing, most wanted first. **/stats**: users, searches, top searches/stories.
- **Requests**: when a new story matches a pending /request, the user is tagged automatically.
- **Report broken link**: button under every delivered link; the admin can delete the story from the report.
- **Anti-abuse**: `SEARCH_COOLDOWN`, `/allowgroup` + `/denygroup` (inside a group) + `/groups`, `/ban` + `/unban`.
- **Force subscribe**: set `FORCE_SUB_CHANNEL` (+ `FORCE_SUB_LINK`), bot must be admin of that channel.
- **/broadcast**, **/backup** (also automatic every `BACKUP_EVERY_HOURS`), **/restore** (reply to a backup file).
- **Mini App**: Trending tab, Favorites tab (star on every story).
- **Hindi search**: Devanagari names match Roman titles and the other way round.
- **Report -> Add new link**: on a broken-link report the admin taps 🔗 Add new link, replies with the corrected link, and the story is fixed instantly (stored in MongoDB). If the same story is also edited/re-indexed from the channel post, update that post too.
