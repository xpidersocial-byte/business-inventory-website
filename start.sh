#!/bin/bash
echo "🚀 Starting FBIHM Inventory Engine..."
# Ensure we are in the app directory
cd /app

# The requirements are already installed during Docker build for speed,
# but we run the app directly using the global python to avoid venv complexity inside a container.
export FLASK_APP=app.py
export FLASK_RUN_HOST=0.0.0.0
export FLASK_RUN_PORT=5000

# Start the application
python3 app.py
