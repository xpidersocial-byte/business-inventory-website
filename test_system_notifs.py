import os
import sys
from bson.objectid import ObjectId
from datetime import datetime, timezone
from flask import Flask, session
from dotenv import load_dotenv
from unittest.mock import patch

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from extensions import mongo, socketio
from core.db import get_notifications_collection, get_users_collection, get_notes_collection
from core.utils import trigger_notification

# Import blueprints to register them in the test app
from routes.system import system_bp, get_notifications
from routes.notes import bulletin_bp, bulletin

def test_admin_to_cashier_notification():
    app = Flask(__name__)
    app.secret_key = "test_secret"
    app.config["MONGO_URI"] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/xpider_db')
    mongo.init_app(app)
    socketio.init_app(app)
    
    # Register blueprints
    app.register_blueprint(system_bp)
    app.register_blueprint(bulletin_bp)
    
    admin_email = "admin@inventory.com"
    cashier_email = "cashier@inventory.com"
    
    with app.app_context():
        print(f"--- Testing Notification Flow: Admin -> Cashier ---")
        
        # Ensure cashier exists and has a last_view for bulletins
        get_users_collection().update_one(
            {"email": cashier_email},
            {"$set": {
                "role": "cashier",
                "last_views.bulletins": datetime.now(timezone.utc)
            }},
            upsert=True
        )
        
        # 1. Admin triggers a bulletin notification
        print(f"\nStep 1: Admin ({admin_email}) triggers a new bulletin notification...")
        with app.test_request_context():
            session['email'] = admin_email
            session['role'] = 'owner'
            
            notif_id = trigger_notification(
                "bulletin", 
                "System Update", 
                "Admin has updated the system settings.", 
                priority="INFO"
            )
            print(f"Notification triggered. ID: {notif_id}")

        # 2. Verify cashier sees this notification via API
        print(f"\nStep 2: Checking notifications for Cashier ({cashier_email})...")
        with app.test_request_context():
            session['email'] = cashier_email
            session['role'] = 'cashier'
            
            response = get_notifications()
            data = response.get_json()
            
            unread_count = data.get('unread_count', 0)
            notifs = data.get('notifications', [])
            
            print(f"Cashier Unread Count: {unread_count}")
            found = False
            for n in notifs:
                if n.get('title') == "System Update":
                    found = True
                    print(f"SUCCESS: Cashier found the admin notification: {n['message']}")
                    break
            
            if not found:
                print("FAILURE: Cashier did not see the notification in the unread list.")
                sys.exit(1)

        # 3. Simulate Cashier visiting the Bulletin Board
        print(f"\nStep 3: Cashier ({cashier_email}) visits the Bulletin Board...")
        with app.test_request_context():
            session['email'] = cashier_email
            session['role'] = 'cashier'
            
            # Patch render_template to avoid context issues
            with patch('routes.notes.render_template') as mocked_render:
                bulletin()
            
            # Now check notifications again
            response = get_notifications()
            data = response.get_json()
            new_unread_count = data.get('unread_count', 0)
            print(f"Cashier Unread Count after visiting: {new_unread_count}")
            
            if new_unread_count < unread_count:
                print("SUCCESS: Notification was automatically marked as read.")
            else:
                print("FAILURE: Notification count did not decrease.")
                sys.exit(1)

        # Clean up
        get_notifications_collection().delete_many({"title": "System Update"})
        print("\n--- Test Completed Successfully ---")

if __name__ == "__main__":
    try:
        test_admin_to_cashier_notification()
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
