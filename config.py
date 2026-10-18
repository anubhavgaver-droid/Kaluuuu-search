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
