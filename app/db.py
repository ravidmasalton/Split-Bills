import os
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from dotenv import load_dotenv

# טוען משתני סביבה מהקובץ .env
load_dotenv()

def default_mongo_url():
    if os.path.exists("/.dockerenv") or os.getenv("RUNNING_IN_DOCKER") == "1":
        return "mongodb://mongo:27017"
    return "mongodb://127.0.0.1:27017"

MONGO_URL = os.getenv("MONGO_URL", default_mongo_url())
print(f"[DB] Connecting to: {MONGO_URL}")

client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
try:
    client.admin.command("ping")
    db = client["splitbills"]
    print("[DB] ✅ Connected to MongoDB")
except ServerSelectionTimeoutError as e:
    print(f"[DB] ❌ Could not connect: {e}")
    raise
