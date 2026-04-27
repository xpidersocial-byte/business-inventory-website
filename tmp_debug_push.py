import json
import os
from pywebpush import webpush, WebPushException
from app import app
from core.utils import get_site_config
from core.db import get_users_collection

def test_push():
    with app.app_context():
        users = list(get_users_collection().find({"role": "owner"}))
        config = get_site_config()
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
                    print(f"Sub {idx} WebPushException: {ex.message}")
                    if ex.response is not None:
                        print(f"   Status: {ex.response.status_code}, Body: {ex.response.text}")
                except Exception as ex:
                    print(f"Sub {idx} Generic Error: {str(ex)}")

if __name__ == '__main__':
    test_push()
