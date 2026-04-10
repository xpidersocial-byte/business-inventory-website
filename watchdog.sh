#!/bin/bash

# --- FBIHM SYSTEM WATCHDOG v3.0 (Enterprise Gunicorn Edition) ---
# Target Server: 74.208.174.70
# Purpose: Auto-restart the website and check MongoDB container status.

# Project Configuration Paths
PROJECT_DIR="/home/eujyrn/Desktop/flask_mongo_app"
VENV_GUNICORN="$PROJECT_DIR/venv/bin/gunicorn"
LOG_FILE="$PROJECT_DIR/watchdog.log"
APP_LOG="$PROJECT_DIR/app.log"

# Navigate to project directory
cd "$PROJECT_DIR"

echo "$(date): Watchdog v3.0 started monitoring..." >> "$LOG_FILE"

# Continuous monitoring loop
while true; do
    # --- 1. MONGODB MONITORING (DOCKER) ---
    if ! docker ps --filter "name=mongodb" --format '{{.Names}}' | grep -w "mongodb" > /dev/null; then
        echo "$(date): MongoDB container is down. Attempting to start..." >> "$LOG_FILE"
        docker start mongodb >> "$LOG_FILE" 2>&1
    fi

    # --- 2. GUNICORN APP MONITORING ---
    # Check if gunicorn is active on the expected config
    if ! pgrep -f "$VENV_GUNICORN" > /dev/null; then
        echo "$(date): Gunicorn Server is down. Restarting..." >> "$LOG_FILE"
        
        # Kill any lingering python processes on port 5000
        fuser -k 5000/tcp >> "$LOG_FILE" 2>&1 || true
        pkill -9 -f "python3 app.py" || true
        pkill -9 -f "python3 run.py" || true
        
        # Start via Gunicorn using the WSGI entry point
        # --worker-class eventlet is required for Socket.IO
        nohup "$VENV_GUNICORN" --worker-class eventlet -w 1 --bind 0.0.0.0:5000 wsgi:application > "$APP_LOG" 2>&1 < /dev/null &
        
        echo "$(date): Gunicorn started." >> "$LOG_FILE"
    fi

    # Wait 15 seconds before next check
    sleep 15
done
