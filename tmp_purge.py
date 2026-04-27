import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)
client = MongoClient(os.getenv("MONGO_URI"))
db = client.get_database()

# Wipe operational data
db.items.delete_many({})
db.purchase.delete_many({})
db.sales.delete_many({})
db.inventory_log.delete_many({})
db.system_logs.delete_many({})

print("Operational Data Purged Successfully!")
