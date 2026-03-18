"""
XPIDER Sample Data Generator
----------------------------
This utility generates a large set of mock inventory items, categories, 
sales records, and restocks. It is primarily used for testing dashboard 
analytics and chart visualizations.
"""

import os
import random
import json
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv
from bson.objectid import ObjectId

# Use relative path for .env
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/flask_todo_db"))
db = client.get_database()

# Collections
items_collection = db.items
categories_collection = db.categories
purchase_collection = db.purchase
inventory_log_collection = db.inventory_log
system_log_collection = db.system_logs

def clear_data():
    """Wipes existing operational data before generation."""
    print("Clearing existing data...")
    items_collection.delete_many({})
    categories_collection.delete_many({})
    purchase_collection.delete_many({})
    inventory_log_collection.delete_many({})
    print("Cleared.")

def generate():
    """Creates 50+ items and 150+ random operational events."""
    categories = [
        "Assorted Item", "Book Prayer", "Religious Book", 
        "Statue", "Necklace", "Rosary", "Crucifix", "Novena"
    ]
    
    # Insert categories
    categories_collection.insert_many([{"name": cat} for cat in categories])
    
    item_names = {
        "Assorted Item": ["Holy Oil", "Light Balls", "Sto. Nino Pocket", "Ref Magnet", "Hanging Amulet", "Holy Water Bottle (S)", "Holy Water Bottle (L)", "Prayer Card"],
        "Book Prayer": ["Ang Pagrosaryo", "Ang Rosaryo ug Mensahe", "Rosary Guide Cebuano", "Deliverance Book", "English Mass", "Word of Fun", "Daily Devotion", "Way of the Cross"],
        "Religious Book": ["Sacred Heart Story", "Coloring Book", "Rainbow of Peace", "Paul the Apostle", "Agimat ni Apo", "Bible Stories", "Lives of Saints", "Gospel Today"],
        "Statue": ["Holy Family (740)", "Guadalupe (700)", "Lourdes (850)", "St. Augustine", "San Vicente Ferrer", "St. Michael", "San Roque", "Sto. Nino Ceramic"],
        "Necklace": ["Gold Necklace (120)", "Gold Necklace (200)", "Scapular Metal", "Cloth Scapular (L)", "Keychain Leather", "Birthstone Large", "Bracelet Gold", "Assorted Necklace"],
        "Rosary": ["Big Rosary", "Gold Rosary", "Wooden Rosary", "Rosary Plastic", "Small Rosary", "Colored Rosary", "Birthstone Rosary", "Crystal Rosary"],
        "Crucifix": ["Plastic Crucifix (S)", "Plastic Crucifix (M)", "Plastic Crucifix (L)", "Wood Crucifix (S)", "Wood Crucifix (M)", "Hanging Crucifix", "Cross Frame", "Metal Cross"],
        "Novena": ["Mother of Perpetual Help", "St. Jude Novena", "Sacred Heart Novena", "Sto. Nino Novena", "Ferrer Novena", "All Types Novena", "Divine Mercy", "St. Joseph Novena"]
    }

    print("Generating 50+ items...")
    items_list = []
    for cat in categories:
        names = item_names.get(cat, ["Generic Item " + str(i) for i in range(5)])
        for name in names:
            cost = round(random.uniform(10, 500), 2)
            retail = round(cost * random.uniform(1.5, 3.0), 2)
            initial_stock = random.randint(5, 100)
            initial_sold = random.randint(0, 50)
            
            items_list.append({
                "name": name,
                "category": cat,
                "cost_price": cost,
                "retail_price": retail,
                "stock": initial_stock,
                "sold": initial_sold,
                "inventory_in": initial_stock + initial_sold,
                "inventory_out": initial_sold
            })
    
    items_collection.insert_many(items_list)
    inserted_items = list(items_collection.find())
    print(f"Inserted {len(inserted_items)} items.")

    users = ["admin@inventory.com", "cashier@inventory.com", "dev@inventory.com"]
    
    print("Generating random sales and restocks...")
    now = datetime.now()
    for _ in range(150):
        item = random.choice(inserted_items)
        event_date = now - timedelta(days=random.randint(0, 60), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        event_date_str = event_date.strftime('%Y-%m-%d %I:%M:%S %p')
        user = random.choice(users)
        event_type = random.choice(["SALE", "RESTOCK", "SALE"])
        qty = random.randint(1, 10)
        
        if event_type == "SALE":
            unit_price = item['retail_price']
            total = round(qty * unit_price, 2)
            purchase_doc = {
                "date": event_date_str, "item_name": item['name'], "qty": qty,
                "previous_stock": item['stock'] + qty, "total_stock": item['stock'],
                "unit_cost": unit_price, "total": total, "status": "Sold", "user": user
            }
            purchase_collection.insert_one(purchase_doc)
            inventory_log_collection.insert_one({
                "item_name": item['name'], "type": "OUT", "qty": qty, "user": user, "timestamp": event_date_str
            })
        else:
            inventory_log_collection.insert_one({
                "item_name": item['name'], "type": "IN", "qty": qty, "user": user, "timestamp": event_date_str
            })

    print("Sample data generation complete.")

if __name__ == "__main__":
    clear_data()
    generate()
