#!/bin/bash

# --- FBIHM SYSTEM WATCHDOG v2.0 ---
# Target Server: 74.208.174.70
# Purpose: Auto-restart the website and check MongoDB container status.

# Project Configuration Paths
PROJECT_DIR="/home/eujyrn/Desktop/flask_mongo_app"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
APP_FILE="app.py"
LOG_FILE="$PROJECT_DIR/watchdog.log"
APP_LOG="$PROJECT_DIR/app.log"

# Navigate to project directory
cd "$PROJECT_DIR"

echo "$(date): Watchdog started monitoring..." >> "$LOG_FILE"

# Continuous monitoring loop
while true; do
    # --- 1. MONGODB MONITORING (DOCKER) ---
    if ! docker ps --filter "name=mongodb" --format '{{.Names}}' | grep -w "mongodb" > /dev/null; then
        echo "$(date): MongoDB container is down. Attempting to start..." >> "$LOG_FILE"
        docker start mongodb >> "$LOG_FILE" 2>&1
    fi

    # --- 2. FLASK APP MONITORING ---
    # Check if the process is active
    if ! pgrep -f "$VENV_PYTHON $APP_FILE" > /dev/null; then
        echo "$(date): Flask App is down. Restarting..." >> "$LOG_FILE"
        # Force clear port 5000 before restart
        fuser -k 5000/tcp >> "$LOG_FILE" 2>&1 || true
        
        # Start the app and fully detach
        nohup "$VENV_PYTHON" "$APP_FILE" > "$APP_LOG" 2>&1 < /dev/null &
        echo "$(date): App restarted." >> "$LOG_FILE"
    fi

    # Wait 10 seconds before next check
    sleep 10
done
