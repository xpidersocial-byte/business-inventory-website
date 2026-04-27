import os
from pymongo import MongoClient
from dotenv import load_dotenv
import sys

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.utils import verify_password

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
users_collection = db.users

test_email = "lyka@xpider.social"
test_password = "password123"

user = users_collection.find_one({"email": test_email})
if user:
    is_valid = verify_password(user.get('password'), test_password)
    print(f"Login test for {test_email} with 'password123': {'SUCCESS' if is_valid else 'FAILED'}")
    print(f"Role: {user.get('role')}, Active: {user.get('active')}, Branch ID: {user.get('branch_id')}")
else:
    print(f"User {test_email} not found!")
