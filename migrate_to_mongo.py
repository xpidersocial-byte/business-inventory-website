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
        print(f"Error: {DB_PATH} not found. Nothing to migrate.")
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
        
        # Convert string IDs back to ObjectIds
        for doc in documents:
            if '_id' in doc:
                doc['_id'] = ObjectId(doc['_id'])
        
        # Insert into MongoDB (using update_one with upsert to avoid duplicates)
        for doc in documents:
            db[collection_name].update_one(
                {'_id': doc['_id']},
                {'$set': doc},
                upsert=True
            )
    
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
