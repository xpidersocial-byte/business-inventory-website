import os
import sys
from flask import Flask
from dotenv import load_dotenv

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from extensions import mongo
from core.db import get_settings_collection

def check_db():
    app = Flask(__name__)
    app.config["MONGO_URI"] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/xpider_db')
    mongo.init_app(app)
    
    with app.app_context():
        settings_coll = get_settings_collection()
        config = settings_coll.find_one({"type": "general"})
        print(f"Config type: {type(config)}")
        if config:
            for k, v in config.items():
                print(f"{k}: {type(v)} = {v}")

if __name__ == "__main__":
    check_db()
