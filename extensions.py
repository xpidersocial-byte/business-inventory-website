from flask_pymongo import PyMongo
from flask_socketio import SocketIO
from apscheduler.schedulers.background import BackgroundScheduler

mongo = PyMongo()
socketio = SocketIO(cors_allowed_origins="*", async_mode='eventlet')
scheduler = BackgroundScheduler(daemon=True)
