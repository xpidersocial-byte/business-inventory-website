from app import app
from core.db import get_purchase_collection
from datetime import datetime, timedelta
import json
from bson import json_util

def check():
    with app.app_context():
        purchases = list(get_purchase_collection().find({}, {'date': 1, 'user': 1, 'total': 1, 'timestamp': 1}).sort('_id', -1).limit(10))
        print(f"RECENT PURCHASES ({len(purchases)} found):")
        for p in purchases:
            print(f"User: {p.get('user')}, Date: {p.get('date') or p.get('timestamp')}, Total: {p.get('total')}")
        
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        print(f"\nTime Threshold (7 days ago): {week_ago}")
        print(f"Current System Time: {now}")

if __name__ == "__main__":
    check()
