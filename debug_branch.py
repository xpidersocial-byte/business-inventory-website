import os
from flask import Flask
from extensions import mongo
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
mongo.init_app(app)

with app.app_context():
    branch = mongo.db.branches.find_one({"name": "Danao"})
    if branch:
        print(f"BRANCH_ID: {branch['_id']}")
        items_count = mongo.db.items.count_documents({"branch_id": branch['_id']})
        items_count_str = mongo.db.items.count_documents({"branch_id": str(branch['_id'])})
        print(f"Items with ObjectId: {items_count}")
        print(f"Items with String ID: {items_count_str}")
        
        # Check some items
        item = mongo.db.items.find_one({"branch_id": {"$exists": True}})
        if item:
            print(f"Example Item branch_id type: {type(item['branch_id'])} value: {item['branch_id']}")
    else:
        print("Branch Danao not found")
