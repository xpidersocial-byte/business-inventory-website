import os
from pymongo import MongoClient
from dotenv import load_dotenv
from bson.objectid import ObjectId

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
users_collection = db.users
branches_collection = db.branches

# Simulate a cashier: lyka@xpider.social
email = "lyka@xpider.social"
user = users_collection.find_one({"email": email})
role = user.get('role')
assigned_branch_id = user.get('branch_id')

print(f"Testing for user: {email}, Role: {role}, Assigned Branch: {assigned_branch_id}")

# Simulate logic from select_branch()
if role == 'cashier' and user and user.get('branch_id'):
    branches = list(branches_collection.find({"_id": ObjectId(user.get('branch_id')), "active": True}))
else:
    branches = list(branches_collection.find({"active": True}).sort("name", 1))

print(f"Number of branches visible to this user: {len(branches)}")
for b in branches:
    print(f"Visible Branch: {b['name']} ({b['_id']})")

if len(branches) == 1 and str(branches[0]['_id']) == assigned_branch_id:
    print("Verification SUCCESS: Cashier only sees their assigned branch.")
else:
    print("Verification FAILED!")
