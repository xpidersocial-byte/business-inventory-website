from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(override=True)

uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(uri)
db = client.get_database()

print(f"Checking database: {db.name}")
print(f"Collections: {db.list_collection_names()}")

items_col = db.items
logs_col = db.inventory_log

items = list(items_col.find({"active": True}))
logs = list(logs_col.find())

print(f"Found {len(items)} active items.")
print(f"Found {len(logs)} logs.")

# If logs are empty but items have stock, let's backfill
if len(logs) == 0 and len(items) > 0:
    print("Logs collection is empty. Backfilling initial stock logs...")
    for item in items:
        if item.get('stock', 0) > 0:
            ts = item.get('created_at', datetime.now())
            if isinstance(ts, datetime):
                ts_str = ts.strftime('%Y-%m-%d %I:%M:%S %p')
            else:
                ts_str = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
                
            log_entry = {
                "item_name": item['name'],
                "type": "IN",
                "qty": item['stock'],
                "user": "System (Backfill)",
                "timestamp": ts_str,
                "new_stock": item['stock'],
                "details": "Initial stock backfill"
            }
            logs_col.insert_one(log_entry)
            print(f"Added IN log for {item['name']} (qty: {item['stock']})")

print("Done.")
