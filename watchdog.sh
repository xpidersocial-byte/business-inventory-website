#!/bin/bash

# Path to the project
PROJECT_DIR="/home/eujyrn/Desktop/flask_mongo_app"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
APP_FILE="$PROJECT_DIR/app.py"
LOG_FILE="$PROJECT_DIR/app_output.log"
MONGOD_BIN="$PROJECT_DIR/mongodb_server/bin/mongod"
DATA_DIR="$PROJECT_DIR/data"
MONGO_LOG="$PROJECT_DIR/mongodb.log"

cd "$PROJECT_DIR"

while true; do
    # 1. Check if MongoDB is running
    if ! pgrep -x "mongod" > /dev/null; then
        echo "$(date): MongoDB is down. Restarting..." >> "$LOG_FILE"
        # Start MongoDB in the background
        "$MONGOD_BIN" --dbpath "$DATA_DIR" --logpath "$MONGO_LOG" --fork >> "$LOG_FILE" 2>&1
        echo "$(date): MongoDB restarted." >> "$LOG_FILE"
        
        # After restarting MongoDB, restart the app to ensure fresh connection
        echo "$(date): Restarting App after MongoDB recovery..." >> "$LOG_FILE"
        pkill -f "$VENV_PYTHON $APP_FILE"
    fi

    # 2. Check if app.py is running
    if ! pgrep -f "$VENV_PYTHON $APP_FILE" > /dev/null; then
        echo "$(date): App is down. Restarting..." >> "$LOG_FILE"
        # Start the app in the background
        nohup "$VENV_PYTHON" "$APP_FILE" >> "$LOG_FILE" 2>&1 &
        echo "$(date): App restarted." >> "$LOG_FILE"
    fi

    # Wait 10 seconds before next check
    sleep 10
done
