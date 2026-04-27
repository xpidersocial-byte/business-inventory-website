#!/bin/bash
echo "🚀 Starting FBIHM Inventory Engine..."
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
cd "$SCRIPT_DIR"

# Clean up any existing processes on port 5000
fuser -k 5000/tcp 2>/dev/null || true

# Start the app using the virtual environment
./venv/bin/python3 run.py
