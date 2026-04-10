#!/bin/bash

# --- FBIHM SYSTEM WATCHDOG v3.0 (Enterprise Gunicorn Edition) ---
# Target Server: 74.208.174.70
# Purpose: Auto-restart the website and check MongoDB container status.

# Project Configuration Paths
PROJECT_DIR="/home/eujyrn/Desktop/flask_mongo_app"
VENV_GUNICORN="$PROJECT_DIR/venv/bin/gunicorn"
LOG_FILE="$PROJECT_DIR/watchdog.log"
APP_LOG="$PROJECT_DIR/app.log"
CODE_HASH_FILE="$PROJECT_DIR/.watchdog_code_hash"

# Paths and exclusions for code-change detection
EXCLUDE_PATHS=("$PROJECT_DIR/venv" "$PROJECT_DIR/data" "$PROJECT_DIR/.git" "$PROJECT_DIR/app.log" "$PROJECT_DIR/watchdog.log")
WATCH_EXTENSIONS='\( -name "*.py" -o -name "*.html" -o -name "*.js" -o -name "*.css" -o -name "*.json" -o -name "*.yml" -o -name "*.yaml" -o -name "*.txt" \)'

# Navigate to project directory
cd "$PROJECT_DIR" || exit 1

echo "$(date): Watchdog v3.0 started monitoring..." >> "$LOG_FILE"

compute_code_hash() {
    find "$PROJECT_DIR" ${EXCLUDE_PATHS[@]/#/ -path } -prune -o -type f $WATCH_EXTENSIONS -print0 \
      | sort -z \
      | xargs -0 sha1sum 2>/dev/null \
      | sha1sum \
      | awk '{print $1}'
}

restart_app() {
    echo "$(date): Restarting Gunicorn due to app state or code update..." >> "$LOG_FILE"
    fuser -k 5000/tcp >> "$LOG_FILE" 2>&1 || true
    pkill -9 -f "python3 app.py" || true
    pkill -9 -f "python3 run.py" || true
    pkill -9 -f "$VENV_GUNICORN" || true

    nohup "$VENV_GUNICORN" --worker-class eventlet -w 1 --bind 0.0.0.0:5000 wsgi:application > "$APP_LOG" 2>&1 < /dev/null &
    sleep 3

    if pgrep -f "$VENV_GUNICORN" > /dev/null; then
        echo "$(date): Gunicorn restarted successfully." >> "$LOG_FILE"
    else
        echo "$(date): Gunicorn failed to restart. Check $APP_LOG." >> "$LOG_FILE"
    fi
}

last_code_hash="$(compute_code_hash)"
echo "$last_code_hash" > "$CODE_HASH_FILE"

# Continuous monitoring loop
while true; do
    # --- 1. MONGODB MONITORING (DOCKER) ---
    if ! docker ps --filter "name=mongodb" --format '{{.Names}}' | grep -w "mongodb" > /dev/null; then
        echo "$(date): MongoDB container is down. Attempting to start..." >> "$LOG_FILE"
        docker start mongodb >> "$LOG_FILE" 2>&1
    fi

    # --- 2. NEW CODE DETECTION ---
    current_code_hash="$(compute_code_hash)"
    if [ "$current_code_hash" != "$last_code_hash" ]; then
        echo "$(date): New code detected on disk. Updating app..." >> "$LOG_FILE"
        last_code_hash="$current_code_hash"
        echo "$current_code_hash" > "$CODE_HASH_FILE"
        restart_app
    fi

    # --- 3. GUNICORN APP MONITORING ---
    if ! pgrep -f "$VENV_GUNICORN" > /dev/null; then
        echo "$(date): Gunicorn Server is down. Restarting..." >> "$LOG_FILE"
        restart_app
    fi

    sleep 15
done
