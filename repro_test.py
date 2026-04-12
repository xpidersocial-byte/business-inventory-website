import os
import sys
from bson.objectid import ObjectId
from datetime import datetime, timezone
from flask import Flask
from dotenv import load_dotenv

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from extensions import mongo
from core.db import get_settings_collection

def test_notification_toggle():
    app = Flask(__name__)
    app.config["MONGO_URI"] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/xpider_db')
    mongo.init_app(app)
    
    with app.app_context():
        settings_coll = get_settings_collection()
        
        # 1. Set to True first
        print("Step 1: Setting 'email_notif_bulletin' to True...")
        settings_coll.update_one({"type": "general"}, {"$set": {"email_notif_bulletin": True}}, upsert=True)
        
        config = settings_coll.find_one({"type": "general"})
        print(f"Current value: {config.get('email_notif_bulletin')}")
        
        # 2. Simulate the 'update_settings' logic for UNCHECKED box
        print("\nStep 2: Simulating UNCHECKED 'email_notif_bulletin' submission...")
        section = "notifications-config"
        # Simulated form data (missing the checkbox)
        form_data = {"section": section} 
        
        upd = {}
        checkbox_map = {
            "notifications-config": [
                "email_notif_stock_in", "email_notif_stock_out", 
                "email_notif_low_stock", "email_notif_sales", 
                "email_notif_login", "email_notif_profile", 
                "email_notif_inventory", "email_notif_bulletin"
            ]
        }

        # My logic from routes/admin.py:
        for k, v in form_data.items():
            if k != 'section':
                upd[k] = True if v == 'on' else v

        if section in checkbox_map:
            for key in checkbox_map[section]:
                if key not in form_data:
                    upd[key] = False

        print(f"Update payload generated: {upd}")
        
        settings_coll.update_one({"type": "general"}, {"$set": upd}, upsert=True)
        
        # 3. Verify
        config = settings_coll.find_one({"type": "general"})
        final_val = config.get('email_notif_bulletin')
        print(f"\nStep 3: Verifying final value: {final_val}")
        
        if final_val == False:
            print("\nSUCCESS: Logic correctly set the value to False.")
        else:
            print("\nFAILURE: Value is still True.")

if __name__ == "__main__":
    try:
        test_notification_toggle()
    except Exception as e:
        print(f"Error during test: {e}")
