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

test_email = "admin@inventory.com"
test_password = "password" # What is the password?

user = users_collection.find_one({"email": test_email})
if user:
    print(f"Stored Password for {test_email}: {user.get('password')}")
    # Let's try some common ones
    for p in ["password", "admin", "123456", "admin123", "pass123"]:
        if verify_password(user.get('password'), p):
            print(f"Login test for {test_email} with '{p}': SUCCESS")
            break
    else:
        print(f"Login test for {test_email} failed for all common passwords.")
else:
    print(f"User {test_email} not found!")
