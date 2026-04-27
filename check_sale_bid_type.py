import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
purchase_collection = db.purchase

first_sale = purchase_collection.find_one()
if first_sale:
    bid = first_sale.get('branch_id')
    print(f"Sale Branch ID Type: {type(bid)}, Value: {bid}")
else:
    print("No sales found in purchase collection.")
