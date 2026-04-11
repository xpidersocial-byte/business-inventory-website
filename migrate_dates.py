import pymongo
from datetime import datetime
import re

client = pymongo.MongoClient('mongodb://127.0.0.1:27017/database?directConnection=true')
db = client.get_database()

def parse_old_date(date_str):
    if not isinstance(date_str, str): return None
    for fmt in ['%Y-%m-%d %I:%M:%S %p', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %I:%M %p']:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

def migrate_collection(collection, field_name):
    print(f"Migrating {collection.name}.{field_name}...")
    count = 0
    for doc in collection.find({field_name: {"$type": "string"}}):
        old_val = doc[field_name]
        dt = parse_old_date(old_val)
        if dt:
            new_val = dt.isoformat()
            collection.update_one({"_id": doc["_id"]}, {"$set": {field_name: new_val}})
            count += 1
    print(f"Updated {count} documents in {collection.name}")

# Migrate purchase
migrate_collection(db.purchase, "date")
migrate_collection(db.purchase, "refunded_at")

# Migrate inventory_log
migrate_collection(db.inventory_log, "timestamp")

# Migrate system_logs
migrate_collection(db.system_logs, "timestamp")

# Migrate undo_logs
migrate_collection(db.undo_logs, "timestamp")

# Migrate users last_views if they are strings
print("Migrating users.last_views...")
user_count = 0
for user in db.users.find({"last_views": {"$exists": True}}):
    last_views = user.get("last_views", {})
    updated = False
    for key, val in last_views.items():
        if isinstance(val, str):
            dt = parse_old_date(val)
            if dt:
                last_views[key] = dt # Set as datetime object for better handling
                updated = True
    if updated:
        db.users.update_one({"_id": user["_id"]}, {"$set": {"last_views": last_views}})
        user_count += 1
print(f"Updated {user_count} users")

client.close()
