import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
settings_collection = db.settings

perms = settings_collection.find_one({"type": "cashier_permissions"})
print(f"Cashier Permissions: {perms}")
