import os
from pymongo import MongoClient
from dotenv import load_dotenv
import sys

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.utils import hash_password, verify_password

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
users_collection = db.users

test_email = "cashier@inventory.com"
new_password = "password123"
hashed = hash_password(new_password)

print(f"Resetting password for {test_email} to '{new_password}' (Hashed: {hashed})")
users_collection.update_one({"email": test_email}, {"$set": {"password": hashed, "active": True}})

# Now verify it
user = users_collection.find_one({"email": test_email})
if user:
    is_valid = verify_password(user.get('password'), new_password)
    print(f"Verification test: {'SUCCESS' if is_valid else 'FAILED'}")
else:
    print("User not found after reset!")
