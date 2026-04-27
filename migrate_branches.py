import pymongo
import os
from dotenv import load_dotenv
from bson.objectid import ObjectId
from datetime import datetime, timezone

# Load environment variables
load_dotenv()

mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/xpider_db')
client = pymongo.MongoClient(mongo_uri)
db = client.get_database()

def migrate():
    print(f"Connecting to: {mongo_uri}")
    
    # 1. Create or Find Danao Branch
    branches_col = db.branches
    danao_branch = branches_col.find_one({"name": "Danao"})
    
    if not danao_branch:
        branch_data = {
            "name": "Danao",
            "location": "Danao City, Cebu",
            "contact": "Contact Info",
            "created_at": datetime.now(timezone.utc),
            "active": True,
            "is_main": True
        }
        res = branches_col.insert_one(branch_data)
        branch_id = res.inserted_id
        print(f"Created Danao branch with ID: {branch_id}")
    else:
        branch_id = danao_branch['_id']
        print(f"Found existing Danao branch with ID: {branch_id}")

    branch_id_str = str(branch_id)

    # 2. Update Collections
    collections_to_update = ['items', 'sales', 'inventory_log', 'users', 'categories', 'notes']
    
    for coll_name in collections_to_update:
        coll = db[coll_name]
        # Only update documents that don't have a branch_id yet
        res = coll.update_many(
            {"branch_id": {"$exists": False}},
            {"$set": {"branch_id": branch_id_str}}
        )
        print(f"Updated {res.modified_count} documents in '{coll_name}' with branch_id: {branch_id_str}")

    print("Migration completed successfully.")
    client.close()

if __name__ == "__main__":
    migrate()
