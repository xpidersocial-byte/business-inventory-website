from app import app
from core.db import get_items_collection, get_purchase_collection, get_inventory_log_collection, get_branches_collection, get_users_collection
from bson.objectid import ObjectId
from datetime import datetime, timedelta, timezone
from core.utils import hash_password
import random

def seed_fake_data():
    with app.app_context():
        items_col = get_items_collection()
        purchases_col = get_purchase_collection()
        logs_col = get_inventory_log_collection()
        branches_col = get_branches_collection()
        users_col = get_users_collection()

        branches = list(branches_col.find())
        if not branches:
            print("No branches found.")
            return

        # 1. Create Fake Cashiers if they don't exist
        fake_cashiers = [
            {"email": "lyka@xpider.social", "name": "Lyka Reyes"},
            {"email": "john@xpider.social", "name": "John Smith"},
            {"email": "sarah@xpider.social", "name": "Sarah Miller"},
            {"email": "ben@xpider.social", "name": "Ben Carter"},
            {"email": "mike@xpider.social", "name": "Mike Ross"},
            {"email": "rachel@xpider.social", "name": "Rachel Zane"},
            {"email": "harvey@xpider.social", "name": "Harvey Specter"},
            {"email": "donna@xpider.social", "name": "Donna Paulsen"},
            {"email": "louis@xpider.social", "name": "Louis Litt"},
            {"email": "jessica@xpider.social", "name": "Jessica Pearson"}
        ]
        
        for c in fake_cashiers:
            if not users_col.find_one({"email": c['email']}):
                users_col.insert_one({
                    "email": c['email'],
                    "password": hash_password("password123"),
                    "role": "cashier",
                    "first_name": c['name'].split(' ')[0],
                    "last_name": c['name'].split(' ')[1],
                    "active": True,
                    "branch_id": str(random.choice(branches)['_id'])
                })

        now = datetime.now(timezone.utc)

        # 2. Seed Sales
        for branch in branches:
            b_id = str(branch['_id'])
            b_name = branch['name']
            
            # Use real items from this branch
            items = list(items_col.find({"branch_id": b_id}))
            if not items: continue

            for _ in range(20): # 20 sales per branch
                item = random.choice(items)
                cashier = random.choice(fake_cashiers)
                
                qty = random.randint(1, 5)
                retail = item.get('retail_price', 100)
                total = qty * retail
                
                sale_date = now - timedelta(days=random.randint(0, 6), hours=random.randint(0, 23))
                date_str = sale_date.strftime('%Y-%m-%d %I:%M:%S %p')

                purchases_col.insert_one({
                    "item_name": item['name'],
                    "qty": qty,
                    "unit_cost": retail,
                    "total": total,
                    "date": date_str,
                    "user": cashier['email'],
                    "branch_id": b_id,
                    "status": "Sold"
                })
                
                logs_col.insert_one({
                    "item_name": item['name'],
                    "type": "OUT",
                    "qty": qty,
                    "user": cashier['email'],
                    "timestamp": date_str,
                    "branch_id": b_id
                })
        
        print("Fake cashier sales seeded successfully.")

if __name__ == "__main__":
    seed_fake_data()
