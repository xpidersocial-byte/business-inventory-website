from app import app
from core.db import get_items_collection, get_categories_collection, get_purchase_collection, get_inventory_log_collection, get_branches_collection, get_users_collection
from core.utils import hash_password
from bson.objectid import ObjectId
from datetime import datetime, timedelta, timezone
import random

def seed_comprehensive_data():
    with app.app_context():
        items_col = get_items_collection()
        cats_col = get_categories_collection()
        purchases_col = get_purchase_collection()
        logs_col = get_inventory_log_collection()
        branches_col = get_branches_collection()
        users_col = get_users_collection()

        print("🚀 Starting Comprehensive Data Seed...")

        # 1. Ensure minimal Branches
        branches = list(branches_col.find({"active": True}))
        if len(branches) < 3:
            print("Creating dummy branches...")
            dummy_branches = [
                {"name": "XPIDER HQ", "location": "Manila Main", "level": 1, "active": True},
                {"name": "Terminal Alpha", "location": "Makati District", "level": 2, "active": True},
                {"name": "Sector 7G", "location": "Pasig Branch", "level": 3, "active": True}
            ]
            for db in dummy_branches:
                if not branches_col.find_one({"name": db["name"]}):
                    branches_col.insert_one(db)
            branches = list(branches_col.find({"active": True}))

        # 2. Setup Cashiers
        print("Setting up Elite Cashiers...")
        fake_cashiers = [
            {"email": "lyka@xpider.social", "name": "Lyka Reyes"},
            {"email": "john@xpider.social", "name": "John Smith"},
            {"email": "sarah@xpider.social", "name": "Sarah Miller"},
            {"email": "ben@xpider.social", "name": "Ben Carter"}
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

        now = datetime.now()

        # 3. Create Categories, Items, and Sales per branch
        for branch in branches:
            b_id = str(branch['_id'])
            b_name = branch['name']
            print(f"Seeding items & sales for branch: {b_name}...")

            # Categories
            cat_list = ["Electronics", "Accessories", "Merchandise"]
            for cat in cat_list:
                if not cats_col.find_one({"name": cat, "branch_id": b_id}):
                    cats_col.insert_one({"name": cat, "branch_id": b_id})

            # Create 10 dummy items
            branch_items = list(items_col.find({"branch_id": b_id}))
            if len(branch_items) < 5:
                for i in range(1, 11):
                    item_name = f"XP-Product {b_name[:3]}-0{i}"
                    
                    # Force some items to be LOW STOCK (under 5) or DORMANT (0 sales)
                    if i <= 2:
                        stock_level = random.randint(0, 3) # Trigger low stock alerts
                    elif i == 3:
                        stock_level = 50 # Dormant stock (high stock, won't generate sales later)
                    else:
                        stock_level = random.randint(20, 100)

                    cost = random.randint(50, 200)
                    retail = cost + random.randint(50, 150)

                    if not items_col.find_one({"name": item_name, "branch_id": b_id}):
                        items_col.insert_one({
                            "name": item_name,
                            "category": random.choice(cat_list),
                            "cost_price": cost,
                            "retail_price": retail,
                            "stock": stock_level,
                            "low_threshold": 5, # Explicit threshold
                            "branch_id": b_id,
                            "added_by": "System",
                            "last_updated": now.strftime('%Y-%m-%d %H:%M:%S')
                        })
                
                branch_items = list(items_col.find({"branch_id": b_id}))

            # Seed massive sales over different periods (Daily, Weekly, Monthly)
            # We skip item index 2 (the 3rd item) to guarantee it becomes a "Dormant Item"
            active_items = [item for idx, item in enumerate(branch_items) if idx != 2]
            
            for _ in range(50): # 50 sales per branch
                item = random.choice(active_items)
                cashier = random.choice(fake_cashiers)
                
                qty = random.randint(1, 3)
                retail = float(item.get('retail_price', 100))
                total = qty * retail
                
                # Generate a random timestamp between now and 40 days ago
                # This guarantees data for Daily (0-1), Weekly (0-7), Monthly (0-30), Yearly
                days_ago = random.randint(0, 40)
                sale_date = now - timedelta(days=days_ago, hours=random.randint(0, 23))
                date_str = sale_date.strftime('%Y-%m-%d %H:%M:%S')

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
                
                # We skip inserting into `inventory_log` so we don't accidentally bloat the audit log heavily,
                # the `purchases_col` is what computes revenue & POS sales.

        print("✅ Seeding complete! Check your leaderboards and stock values.")
        print("Note: Start the browser and process a REAL SALE via the POS to test real-time Web Push Notifications!")

if __name__ == "__main__":
    seed_comprehensive_data()
