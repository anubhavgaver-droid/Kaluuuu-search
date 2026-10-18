import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    API_ID = int(os.environ["API_ID"])
    API_HASH = os.environ["API_HASH"]
    BOT_TOKEN = os.environ["BOT_TOKEN"]
    MONGO_URI = os.environ["MONGO_URI"]
    DB_NAME = os.getenv("DB_NAME", "SearchBot")
    PORT = int(os.getenv("PORT", 8080))  # Render sets PORT automatically
    ADMINS = [int(x) for x in os.getenv("ADMINS", "").replace(",", " ").split()]

    # Search tuning
    EXACT_SCORE = int(os.getenv("EXACT_SCORE", 88))  # >= this: show only the exact match
    MIN_SCORE = int(os.getenv("MIN_SCORE", 55))      # below this: not found
    MAX_RESULTS = int(os.getenv("MAX_RESULTS", 3))   # suggestions to show

    # Auto-delete bot/search messages after N seconds (0 = off)
    AUTO_DELETE = int(os.getenv("AUTO_DELETE_SECONDS", 300))
    # In groups only strong matches get a reply (avoids answering normal chat)
    GROUP_MIN_SCORE = int(os.getenv("GROUP_MIN_SCORE", 65))
    BOT_USERNAME = ""  # filled at startup
    SUGGEST_COUNT = int(os.getenv("SUGGEST_COUNT", 15))  # max AI suggestions (paginated)
    RELAX_SCORE = int(os.getenv("RELAX_SCORE", 40))     # last-chance AI pass in PM
    PAGE_SIZE = int(os.getenv("PAGE_SIZE", 5))          # results per page
    TAG_MAX = int(os.getenv("TAG_MAX", 60))             # max results for a #hashtag search
    # story requests go to this chat/channel id (blank = send to every admin in ADMINS)
    REQUEST_CHAT_ID = int(os.getenv("REQUEST_CHAT_ID") or 0)
    REQUEST_LIMIT = int(os.getenv("REQUEST_LIMIT", 5))  # requests per user per 24h
