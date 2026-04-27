import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
users_collection = db.users

print(f"Checking database: {db.name}")
print(f"Total users: {users_collection.count_documents({})}")

cashiers = list(users_collection.find({"role": "cashier"}))
print(f"Total cashiers: {len(cashiers)}")

for cashier in cashiers:
    print(f"Email: {cashier.get('email')}, Role: {cashier.get('role')}, Password Format: {'Hashed' if cashier.get('password', '').startswith(('scrypt:', 'pbkdf2:')) else 'Plain/Unknown'}")
