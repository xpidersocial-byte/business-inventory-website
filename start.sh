#!/bin/bash
echo "🚀 Starting FBIHM Inventory Engine..."
# Detect if in Docker or Host
if [ -d "/app" ]; then
    cd /app
    python3 app.py
else
    cd /home/eujyrn/Desktop/flask_mongo_app
    source venv/bin/activate
    # Use python directly since socketio.run handles gevent
    python3 app.py
fi
