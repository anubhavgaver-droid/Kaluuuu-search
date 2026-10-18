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
    GROUP_MIN_SCORE = int(os.getenv("GROUP_MIN_SCORE", 75))
    BOT_USERNAME = ""  # filled at startup
