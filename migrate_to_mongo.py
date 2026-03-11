"""
XPIDER Migration Utility: NoSQL Transition (v2.0)
-----------------------------------------------
This script migrates data from 'persist_db.json' to MongoDB.
Updated to handle missing _id fields and map 'username' to 'email'.
"""

import json
import os
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/flask_todo_db")
DB_PATH = 'persist_db.json'

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found.")
        return

    print(f"Connecting to MongoDB at {MONGO_URI}...")
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()

    with open(DB_PATH, 'r') as f:
        data = json.load(f)

    for collection_name, documents in data.items():
        if not documents:
            continue
        
        print(f"Migrating {len(documents)} documents to '{collection_name}'...")
        
        for doc in documents:
            # Handle user field mapping (username -> email)
            if collection_name == 'users':
                if 'username' in doc and 'email' not in doc:
                    # If it's the admin or cashier from persist_db, give them full emails
                    if doc['username'] == 'admin':
                        doc['email'] = 'admin@inventory.com'
                    elif doc['username'] == 'cashier':
                        doc['email'] = 'cashier@inventory.com'
                    else:
                        doc['email'] = f"{doc['username']}@inventory.com"
                
                # Filter for upsert based on email
                filter_query = {'email': doc.get('email')}
            else:
                # Filter for upsert based on _id if present, else name
                if '_id' in doc:
                    doc['_id'] = ObjectId(doc['_id'])
                    filter_query = {'_id': doc['_id']}
                elif 'name' in doc:
                    filter_query = {'name': doc['name']}
                else:
                    # Fallback
                    filter_query = doc

            db[collection_name].update_one(
                filter_query,
                {'$set': doc},
                upsert=True
            )
    
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
