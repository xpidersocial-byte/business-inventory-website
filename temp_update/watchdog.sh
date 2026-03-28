#!/bin/bash

# --- FBIHM SYSTEM WATCHDOG ---
# Purpose: Ensures 24/7 uptime for both the MongoDB database 
# and the Flask application by monitoring processes and 
# auto-restarting them if they go down.

# Project Configuration Paths
PROJECT_DIR="/home/fbihm/business-inventory-website"
VENV_PYTHON="/home/fbihm/business-inventory-website/venv/bin/python"
APP_FILE="$PROJECT_DIR/app.py"
LOG_FILE="$PROJECT_DIR/app_output.log"
MONGOD_BIN="$PROJECT_DIR/mongodb_server/bin/mongod"
DATA_DIR="$PROJECT_DIR/data"
MONGO_LOG="$PROJECT_DIR/mongodb.log"

# Navigate to project directory
cd "$PROJECT_DIR"

echo "$(date): Watchdog started monitoring..." >> "$LOG_FILE"

# Continuous monitoring loop
while true; do
    # --- 1. MONGODB MONITORING ---
    # Check if the 'mongod' process is active
    if ! pgrep -x "mongod" > /dev/null; then
        echo "$(date): MongoDB is down. Restarting..." >> "$LOG_FILE"
        # Start MongoDB as a background fork
        "$MONGOD_BIN" --dbpath "$DATA_DIR" --logpath "$MONGO_LOG" --fork >> "$LOG_FILE" 2>&1
        echo "$(date): MongoDB restarted." >> "$LOG_FILE"
        
        # Dependency check: If DB was down, the app likely lost its connection.
        # We kill the app process here to trigger a restart in the next step.
        echo "$(date): Restarting App after MongoDB recovery..." >> "$LOG_FILE"
        pkill -f "$VENV_PYTHON $APP_FILE"
    fi

    # --- 2. FLASK APP MONITORING ---
    # Check if the specific app.py instance is running
    if ! pgrep -f "$VENV_PYTHON $APP_FILE" > /dev/null; then
        echo "$(date): App is down. Restarting..." >> "$LOG_FILE"
        # Start the Flask app using nohup to prevent it from closing with the shell
        # Redirect all output to the system log file
        nohup "$VENV_PYTHON" "$APP_FILE" >> "$LOG_FILE" 2>&1 &
        echo "$(date): App restarted." >> "$LOG_FILE"
    fi

    # System throttle: wait 10 seconds before the next health check
    sleep 10
done
