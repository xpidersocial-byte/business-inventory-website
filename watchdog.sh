#!/bin/bash

# --- FBIHM SYSTEM WATCHDOG v3.1 (Fixed Edition) ---
# Purpose: Auto-restart the website and check MongoDB container status.

# Project Configuration Paths
PROJECT_DIR="/home/eujyrn/Desktop/FBIHM-PROJECT (copy 1)"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
LOG_FILE="$PROJECT_DIR/watchdog.log"
APP_LOG="$PROJECT_DIR/app.log"
CODE_HASH_FILE="$PROJECT_DIR/.watchdog_code_hash"

# Navigate to project directory
cd "$PROJECT_DIR" || exit 1

echo "$(date): Watchdog v3.1 started monitoring..." >> "$LOG_FILE"

compute_code_hash() {
    # Using a simpler find that avoids the complex variable expansion issues
    find "$PROJECT_DIR" \
        \( -path "$PROJECT_DIR/venv" -o -path "$PROJECT_DIR/data" -o -path "$PROJECT_DIR/.git" -o -path "$LOG_FILE" -o -path "$APP_LOG" \) -prune \
        -o -type f \( -name "*.py" -o -name "*.html" -o -name "*.js" -o -name "*.css" -o -name "*.json" -o -name "*.yml" -o -name "*.yaml" -o -name "*.txt" \) -print0 \
        | sort -z | xargs -0 sha1sum 2>/dev/null | sha1sum | awk '{print $1}'
}

restart_app() {
    echo "$(date): Restarting App due to app state or code update..." >> "$LOG_FILE"
    # Kill any process on port 5000
    fuser -k 5000/tcp >> "$LOG_FILE" 2>&1 || true
    pkill -9 -f "run.py" || true
    pkill -9 -f "app.py" || true

    nohup "$VENV_PYTHON" run.py > "$APP_LOG" 2>&1 < /dev/null &
    echo $! > app.pid
    sleep 5

    if pgrep -f "run.py" > /dev/null; then
        echo "$(date): App started successfully." >> "$LOG_FILE"
    else
        echo "$(date): App failed to restart. Check $APP_LOG." >> "$LOG_FILE"
    fi
}

last_code_hash="$(compute_code_hash)"
echo "$last_code_hash" > "$CODE_HASH_FILE"

# Continuous monitoring loop
while true; do
    # --- 1. MONGODB MONITORING ---
    if command -v docker >/dev/null 2>&1; then
        if ! docker ps --filter "name=mongodb" --format '{{.Names}}' | grep -w "mongodb" > /dev/null 2>&1; then
            echo "$(date): MongoDB container is down. Attempting to start..." >> "$LOG_FILE"
            sudo docker start mongodb >> "$LOG_FILE" 2>&1 || echo "Could not start mongodb container" >> "$LOG_FILE"
        fi
    fi

    # --- 2. NEW CODE DETECTION ---
    current_code_hash="$(compute_code_hash)"
    if [ "$current_code_hash" != "$last_code_hash" ]; then
        echo "$(date): New code detected on disk. Updating app..." >> "$LOG_FILE"
        last_code_hash="$current_code_hash"
        echo "$current_code_hash" > "$CODE_HASH_FILE"
        restart_app
    fi

    # --- 3. APP MONITORING ---
    if ! pgrep -f "run.py" > /dev/null; then
        echo "$(date): App is down. Restarting..." >> "$LOG_FILE"
        restart_app
    fi

    sleep 15
done
