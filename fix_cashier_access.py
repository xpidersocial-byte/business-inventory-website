import os
from pymongo import MongoClient
from dotenv import load_dotenv
import sys

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.utils import hash_password

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
users_collection = db.users
settings_collection = db.settings

print("--- Updating Cashier Permissions ---")
cashier_perms = {
    "dashboard": True,
    "pos": True,
    "items_master": True,
    "sales_ledger": True,
    "sales_summary": True,
    "restock": True,
    "bulletin_board": True,
    "legend": True,
    "developer_portal": False,
    "live_debug": False,
    "health_scanner": False,
    "admin_accounts": False,
    "general_setup": False,
    "system_logs": False,
    "setup_identity": False,
    "setup_localization": False,
    "setup_logic": False,
    "setup_users": False,
    "setup_categories": False,
    "setup_themes": False,
    "setup_advanced": False,
    "setup_assets": False,
    "setup_backup": False,
    "setup_danger_zone": False,
    "setup_smtp": False,
    "setup_notifications": False
}
settings_collection.update_one(
    {"type": "cashier_permissions"}, 
    {"$set": cashier_perms}, 
    upsert=True
)
print("Point of Sale and other modules enabled for Cashiers.")

print("\n--- Updating User Roles and Status ---")
# 1. Promote admin@inventory.com to owner
admin_user = users_collection.find_one({"email": "admin@inventory.com"})
if admin_user:
    users_collection.update_one(
        {"email": "admin@inventory.com"},
        {"$set": {
            "role": "owner",
            "active": True,
            "password": hash_password("pass123")
        }}
    )
    print("Promoted admin@inventory.com to Owner and updated password.")

# 2. Ensure all users are Active
result = users_collection.update_many(
    {}, 
    {"$set": {"active": True}}
)
print(f"Set 'active: True' for {result.modified_count} users.")

# 3. Check for users with missing essential fields
for user in users_collection.find():
    if not user.get('role'):
        users_collection.update_one({"_id": user['_id']}, {"$set": {"role": "cashier"}})
        print(f"Fixed missing role for {user.get('email')}")

print("\n--- Repair Complete ---")
