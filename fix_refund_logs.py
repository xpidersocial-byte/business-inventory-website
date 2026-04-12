from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv(override=True)

uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(uri)
db = client.get_database()

logs_col = db.inventory_log

# Find all IN logs that mention Refund in details
cursor = logs_col.find({"type": "IN", "details": {"$regex": "Refund", "$options": "i"}})
count = 0
for log in cursor:
    logs_col.update_one({"_id": log["_id"]}, {"$set": {"is_refund": True}})
    count += 1

print(f"Updated {count} refund logs.")
