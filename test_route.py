import os
import sys
from flask import session
from datetime import datetime, timezone

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app
from core.db import get_inventory_log_collection, get_items_collection

def test_generate_report_route():
    print("Starting Route Test: /sales/generate-report?view=monthly&format=pdf")
    
    # 1. Ensure we have at least one piece of data to report on
    with app.app_context():
        log_coll = get_inventory_log_collection()
        item_coll = get_items_collection()
        
        # Check if any OUT logs exist
        count = log_coll.count_documents({"type": "OUT"})
        print(f"Found {count} OUT logs in database.")
        
        if count == 0:
            print("Injecting dummy data for test...")
            item_coll.insert_one({
                "name": "Test Item",
                "retail_price": 100.0,
                "cost_price": 50.0,
                "active": True
            })
            log_coll.insert_one({
                "item_name": "Test Item",
                "type": "OUT",
                "qty": 1,
                "timestamp": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
            })

    # 2. Use Test Client
    client = app.test_client()
    
    with client.session_transaction() as sess:
        sess['email'] = 'admin@inventory.com'
        sess['role'] = 'owner'
        sess['_fresh'] = True

    try:
        response = client.get('/sales/generate-report?view=monthly&format=pdf')
        
        print(f"Response Status: {response.status_code}")
        print(f"Content Type: {response.mimetype}")
        
        if response.status_code == 200 and response.mimetype == 'application/pdf':
            print("\nSUCCESS: PDF generated successfully via route.")
        elif response.status_code == 302:
            print(f"\nREDIRECTED to: {response.location}")
            print("This usually happens if no data was found for the period.")
        else:
            print(f"\nFAILURE: Unexpected response.")
            # If it's a 500 error, we'll see it here if debug is off, 
            # but if we run this script it should throw the actual exception if not caught.
            
    except Exception as e:
        print(f"\nCRASH DETECTED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Disable actual email sending for test if needed, 
    # but here we just want to see if it generates.
    test_generate_report_route()
