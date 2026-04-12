import pymongo
import os
import sys
from dotenv import load_dotenv

# Add current directory to path so we can import core.utils
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.utils import hash_password

# Load environment variables from .env file
load_dotenv()

mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/xpider_db')
# Check if user rules URI should be used
if "mongodb+srv" not in mongo_uri and "xpiderdata" not in mongo_uri:
    print("WARNING: Using local MongoDB URI. ATLAS URI detected in rules but not in .env")

client = pymongo.MongoClient(mongo_uri)
db = client.get_database()
users = db.users

email = "bejasadhev@gmail.com"
password = "admin_password_123" # Temporary password
hashed_password = hash_password(password)

user_data = {
    "email": email,
    "password": hashed_password,
    "role": "owner",
    "first_name": "Admin",
    "last_name": "User",
    "theme": "facebook",
    "active": True
}

# Check if user exists
existing_user = users.find_one({"email": email})
if existing_user:
    print(f"User {email} already exists. Updating role to owner and resetting password (hashed).")
    users.update_one({"email": email}, {"$set": {"role": "owner", "password": hashed_password, "active": True}})
else:
    users.insert_one(user_data)
    print(f"Admin user created (with hashed password): {email} / {password}")

client.close()
