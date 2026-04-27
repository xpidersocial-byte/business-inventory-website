import eventlet
eventlet.monkey_patch(all=True)

import json
import os
from pywebpush import webpush, WebPushException
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

def push_worker(sub, payload, vapid_private, vapid_claims):
    return webpush(
        subscription_info=sub,
        data=payload,
        vapid_private_key=vapid_private,
        vapid_claims=vapid_claims
    )

def test_push():
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client.get_database()
    users_col = db.users
    settings_col = db.settings
    
    users = list(users_col.find({"role": "owner"}))
    config = settings_col.find_one({"type": "general"}) or {}
    vapid_private = os.getenv("VAPID_PRIVATE_KEY") or config.get('vapid_private_key')
    vapid_email = os.getenv("VAPID_CLAIM_EMAIL") or config.get('vapid_claim_email', 'admin@inventory.com')
    
    vapid_claims = {"sub": f"mailto:{vapid_email}"}

    for user in users:
        subs = user.get("push_subscriptions", [])
        for idx, sub in enumerate(subs):
            try:
                # Use tpool
                res = eventlet.tpool.execute(push_worker, sub, json.dumps({"title": "TPOOL Test", "body": "Testing eventlet.tpool", "url": "/"}), vapid_private, vapid_claims)
                print(f"Sub {idx}: Success!")
            except Exception as ex:
                print(f"Sub {idx} Error: {str(ex)}")

if __name__ == '__main__':
    test_push()
