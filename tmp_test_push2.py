from app import app
from core.utils import generate_sales_summary, trigger_notification, send_push_notification
from core.db import get_items_collection, get_users_collection

print("--- Testing Low Stock and Push Notifications ---")

with app.test_request_context():
    print("\n1. Testing Daily Summary Alert...")
    generate_sales_summary("Daily")
    print("Success: Daily Summary generator executed.")

    print("\n2. Testing Low Stock Alert...")
    items_col = get_items_collection()
    item = items_col.find_one({})
    
    if item:
        print(f"Triggering stock alert for item: {item.get('name')}")
        trigger_notification(
            "stock_alert",
            "Low Stock Warning",
            f"Item '{item['name']}' is running low (TEST).",
            {"item_id": str(item['_id']), "stock": 1},
            priority="WARNING"
        )
        users = list(get_users_collection().find({"role": "owner"}))
        target_emails = [u.get('email') for u in users if u.get('email')]
        send_push_notification("FBIHM Alert: Simulated Low Stock", "This is a test low stock payload.", target_emails)
        print("Success: Low Stock notification flow triggered.")
        
    print("\n--- Tests Completed ---")
