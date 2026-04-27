import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database")
client = MongoClient(mongo_uri)
db = client.get_database()
logs_collection = db.system_logs

failed_logins = list(logs_collection.find({"action": "LOGIN_FAILED"}).sort("timestamp", -1).limit(20))
print(f"Recent failed logins: {len(failed_logins)}")
for log in failed_logins:
    print(f"Time: {log.get('timestamp')}, Details: {log.get('details')}")
