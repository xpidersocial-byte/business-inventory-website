import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
users_collection = db.users

all_users = list(users_collection.find())
print(f"Total users: {len(all_users)}")

for user in all_users:
    print(f"Email: {user.get('email')}, Role: {user.get('role')}, Active: {user.get('active')}")
