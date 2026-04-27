import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
users_collection = db.users
branches_collection = db.branches

print("--- Branches ---")
for branch in branches_collection.find():
    print(f"ID: {branch['_id']}, Name: {branch['name']}, Active: {branch.get('active')}")

print("\n--- Users and assigned Branch IDs ---")
for user in users_collection.find():
    print(f"Email: {user.get('email')}, Role: {user.get('role')}, Branch ID: {user.get('branch_id')}")
