#!/bin/bash

# Path to the project
PROJECT_DIR="/home/eujyrn/Desktop/flask_mongo_app"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
APP_FILE="$PROJECT_DIR/app.py"
LOG_FILE="$PROJECT_DIR/app_output.log"

cd "$PROJECT_DIR"

while true; do
    # Check if app.py is running
    if ! pgrep -f "$VENV_PYTHON $APP_FILE" > /dev/null; then
        echo "$(date): App is down. Restarting..." >> "$LOG_FILE"
        # Start the app in the background
        nohup "$VENV_PYTHON" "$APP_FILE" >> "$LOG_FILE" 2>&1 &
        echo "$(date): App restarted." >> "$LOG_FILE"
    fi
    # Wait 10 seconds before next check
    sleep 10
done
