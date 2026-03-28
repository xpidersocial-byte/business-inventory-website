import pymongo
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/xpider_db')
client = pymongo.MongoClient(mongo_uri)
db = client.get_database()
users = db.users

email = "bejasadhev@gmail.com"
password = "admin_password_123" # Temporary password

user_data = {
    "email": email,
    "password": password,
    "role": "owner",
    "first_name": "Admin",
    "last_name": "User",
    "theme": "facebook",
    "active": True
}

# Check if user exists
existing_user = users.find_one({"email": email})
if existing_user:
    print(f"User {email} already exists. Updating role to owner and resetting password.")
    users.update_one({"email": email}, {"$set": {"role": "owner", "password": password, "active": True}})
else:
    users.insert_one(user_data)
    print(f"Admin user created: {email} / {password}")

client.close()
