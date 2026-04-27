import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
settings_collection = db.settings

config = settings_collection.find_one({"type": "general"})
print(f"Maintenance Mode: {config.get('maintenance_mode')}")
