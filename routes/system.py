from flask import Blueprint, jsonify
import psutil
import socket
import requests
from datetime import datetime
from core.db import get_system_log_collection
from core.middleware import login_required

system_bp = Blueprint('system', __name__)

@system_bp.route('/system-info')
@login_required
def system_info():
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Try to get public IP
    try:
        public_ip = requests.get('https://api.ipify.org', timeout=1).text
    except:
        public_ip = "Offline"

    local_ip = socket.gethostbyname(socket.gethostname())

    return jsonify({
        "cpu": cpu,
        "ram_percent": ram.percent,
        "ram_used": f"{ram.used / (1024**3):.1f} GB",
        "ram_total": f"{ram.total / (1024**3):.1f} GB",
        "disk_percent": disk.percent,
        "disk_free": f"{disk.free / (1024**3):.1f} GB",
        "public_ip": public_ip,
        "local_ip": local_ip
    })

@system_bp.route('/latest-log')
@login_required
def latest_log():
    logs_col = get_system_log_collection()
    log = logs_col.find_one(sort=[("timestamp", -1)])
    if log:
        return jsonify({
            "action": log.get('action'),
            "details": log.get('details'),
            "timestamp": log.get('timestamp'),
            "email": log.get('email')
        })
    return jsonify({})
