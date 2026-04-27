import json
import os
import requests
from pywebpush import webpush, WebPushException
from pymongo import MongoClient
import urllib.parse
from dotenv import load_dotenv

load_dotenv(override=True)

def test_push():
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client.get_database()
    users_col = db.users
    settings_col = db.settings
    
    users = list(users_col.find({"role": "owner"}))
    config = settings_col.find_one({"type": "general"}) or {}
    vapid_private = os.getenv("VAPID_PRIVATE_KEY") or config.get('vapid_private_key')
    vapid_email = os.getenv("VAPID_CLAIM_EMAIL") or config.get('vapid_claim_email', 'admin@inventory.com')
    
    print(f"VAPID Private loaded: {bool(vapid_private)}")
    vapid_claims = {"sub": f"mailto:{vapid_email}"}

    if not vapid_private:
        print("ERROR: No VAPID Private key.")
        return

    for user in users:
        subs = user.get("push_subscriptions", [])
        print(f"\nUser {user.get('email')} has {len(subs)} subscriptions.")
        for idx, sub in enumerate(subs):
            try:
                res = webpush(
                    subscription_info=sub,
                    data=json.dumps({"title": "Direct Test", "body": "This is a direct VAPID test payload.", "url": "/"}),
                    vapid_private_key=vapid_private,
                    vapid_claims=vapid_claims
                )
                print(f"Sub {idx}: Success! (Res: {res.status_code if hasattr(res, 'status_code') else 'OK'})")
            except WebPushException as ex:
                if ex.response is not None and ex.response.status_code in [410, 404]:
                    print(f"Sub {idx}: Subscription expired (410/404)")
                else:
                    print(f"Sub {idx} WebPushException: {ex.message}")
            except Exception as ex:
                print(f"Sub {idx} Generic Error: {str(ex)}")

if __name__ == '__main__':
    test_push()
