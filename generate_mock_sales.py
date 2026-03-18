from pymongo import MongoClient
from datetime import datetime, timedelta
import random

# Connection - Standard non-atlas for mock script to avoid SSL handshake issues in this specific env
# Using localhost since the app.py also has a fallback to localhost
client = MongoClient("mongodb://localhost:27017/flask_todo_db")
db = client['flask_todo_db']
items_col = db['items']
logs_col = db['inventory_log'] # Match app.py collection name

# Get items
items = list(items_col.find())
if not items:
    # Try the remote cluster if local is empty (with SSL ignore)
    print("Local DB empty, trying remote...")
    uri = "mongodb+srv://xpiderdata:9NT217K59Opc7RLg@data.vj1b80q.mongodb.net/?appName=data&tlsAllowInvalidCertificates=true"
    client = MongoClient(uri)
    db = client['inventory_db']
    items_col = db['items']
    logs_col = db['inventory_log']
    items = list(items_col.find())

if not items:
    print("No items found to generate sales for.")
    exit()

# Generate logs for last 12 months
now = datetime.now()

print(f"Generating mock sales for {len(items)} items...")

logs = []
total_sales = 0

# 500 random sale events
for i in range(500):
    item = random.choice(items)
    days_ago = random.randint(0, 365)
    # Bias towards recent
    if random.random() > 0.7:
        days_ago = random.randint(0, 30)
    
    sale_date = now - timedelta(days=days_ago, hours=random.randint(0,23), minutes=random.randint(0,59))
    qty = random.randint(1, 5)
    
    logs.append({
        "item_name": item['name'],
        "qty": qty,
        "type": "OUT",
        "user": "System Mock",
        "timestamp": sale_date.strftime('%Y-%m-%d %I:%M:%S %p')
    })
    total_sales += qty

if logs:
    logs_col.insert_many(logs)
    print(f"Successfully inserted {len(logs)} sale events (Total Qty: {total_sales})")
else:
    print("No logs generated.")
