import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
users_collection = db.users

for user in users_collection.find({"role": "cashier"}):
    print(f"Email: {user.get('email')}, Password: {user.get('password')[:20]}...")
