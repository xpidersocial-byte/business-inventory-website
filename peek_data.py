from flask import Flask
from extensions import mongo
from core.db import get_items_collection, get_inventory_log_collection
import os
from datetime import datetime

app = Flask(__name__)
# The MongoDB connection string is in the GEMINI.md file: mongodb+srv://xpiderdata:9NT217K59Opc7RLg@data.vj1b80q.mongodb.net/?appName=data
app.config["MONGO_URI"] = "mongodb+srv://xpiderdata:9NT217K59Opc7RLg@data.vj1b80q.mongodb.net/test?appName=data"
mongo.init_app(app)

with app.app_context():
    items_collection = get_items_collection()
    inventory_log_collection = get_inventory_log_collection()
    
    print("--- 5 Items ---")
    items = list(items_collection.find().limit(5))
    for item in items:
        print(item)
        
    print("\n--- 5 Inventory Logs ---")
    logs = list(inventory_log_collection.find().limit(5))
    for log in logs:
        print(log)
