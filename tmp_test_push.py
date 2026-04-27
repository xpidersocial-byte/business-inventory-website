from app import app
from core.utils import generate_sales_summary, send_push_notification, trigger_notification, update_item_stock
from core.db import get_items_collection, get_users_collection

print("--- Testing Low Stock and Push Notifications ---")

with app.app_context():
    print("\n1. Testing Daily Summary Alert...")
    try:
        generate_sales_summary("Daily")
        print("Success: Daily Summary generator executed (check logs/device if subscribed).")
    except Exception as e:
        print(f"Error executing Daily Summary: {e}")

    print("\n2. Testing Low Stock Alert...")
    try:
        items_col = get_items_collection()
        # Find any item
        item = items_col.find_one({})
        if item:
            print(f"Triggering stock out for item: {item.get('name')}")
            # Out 1 quantity, but force a manual trigger just in case
            trigger_notification(
                "stock_alert",
                "Simulated Low Stock Warning",
                f"Item '{item['name']}' is running low (TEST).",
                {"item_id": str(item['_id']), "stock": 1},
                priority="WARNING"
            )
            
            # test push payload direct
            users = list(get_users_collection().find({"role": "owner"}))
            target_emails = [u.get('email') for u in users if u.get('email')]
            send_push_notification("FBIHM Alert: Simulated Low Stock", "This is a test low stock payload.", target_emails)
            
            print("Success: Low Stock notification flow triggered.")
        else:
            print("No items found to trigger stock alert.")
    except Exception as e:
        print(f"Error testing Low Stock: {e}")
        
    print("\n--- Tests Completed ---")
