#!/bin/bash
echo "🚀 Starting FBIHM Inventory Engine..."
# Detect if in Docker or Host
if [ -d "/app" ]; then
    cd /app
    python3 app.py
else
    # Use current directory
    SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
    cd "$SCRIPT_DIR"
    source venv/bin/activate
    # Use python directly since socketio.run handles gevent
    python3 app.py
fi
