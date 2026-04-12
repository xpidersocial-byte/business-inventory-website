import pymongo
from bson.objectid import ObjectId
from datetime import datetime, timezone
import os

def test_notification():
    # Connect to local mongo (assuming same as in create_admin.py)
    mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/xpider_db')
    client = pymongo.MongoClient(mongo_uri)
    db = client.get_database()
    
    # Collections
    items_col = db.items
    notifs_col = db.notifications
    
    print("--- Notification System Test ---")
    
    # 1. Create a test item
    test_name = f"Test Item {datetime.now().timestamp()}"
    print(f"Creating test item: {test_name}")
    
    res = items_col.insert_one({
        "name": test_name,
        "category": "Testing",
        "menu": "None",
        "cost_price": 10.0,
        "retail_price": 20.0,
        "stock": 5,
        "active": True,
        "created_at": datetime.now(timezone.utc)
    })
    item_id = res.inserted_id
    print(f"Item created with ID: {item_id}")
    
    # 2. Simulate the logic from routes/inventory.py
    print("Simulating notification insertion...")
    notifs_col.insert_one({
        "type": "item_added",
        "title": "New Item Added",
        "message": f"'{test_name}' was added to the inventory.",
        "item_id": str(item_id),
        "author": "tester@example.com",
        "created_at": datetime.now(timezone.utc),
        "read_by": ["tester@example.com"]
    })
    
    # 3. Verify the notification exists
    print("Verifying notification in DB...")
    notif = notifs_col.find_one({"item_id": str(item_id)})
    if notif:
        print("SUCCESS: Notification found in database!")
        print(f"Notification details: {notif}")
    else:
        print("FAILURE: Notification not found!")
        
    # Clean up
    items_col.delete_one({"_id": item_id})
    notifs_col.delete_one({"item_id": str(item_id)})
    print("Cleanup finished.")
    
    client.close()

if __name__ == "__main__":
    test_notification()
