from flask import Blueprint, jsonify, session, request
import psutil
import socket
import requests
import platform
import sys
from datetime import datetime, timezone, timedelta
from bson.objectid import ObjectId
from copy import deepcopy
from core.db import (
    get_system_log_collection, get_users_collection, get_notes_collection, 
    get_items_collection, get_inventory_log_collection, get_purchase_collection,
    get_settings_collection, get_sales_collection, get_notifications_collection
)
from core.middleware import login_required
from core.utils import calculate_item_metrics

system_bp = Blueprint('system', __name__)

@system_bp.route('/api/notifications')
@login_required
def get_notifications():
    user_email = session.get('email')
    
    branch_id = session.get('branch_id')
    
    # 1. Persistent Notifications (Item Added, Sales, Restocks) - filtered by branch
    notifs_col = get_notifications_collection()
    notif_query = {"read_by": {"$ne": user_email}}
    if branch_id:
        notif_query["branch_id"] = branch_id
    
    unread_notifs = list(notifs_col.find(notif_query).sort("created_at", -1))
    
    # Dynamic Counts for Sidebar
    new_items_count = sum(1 for n in unread_notifs if n['type'] in ['item_added', 'item_deleted', 'item_edited', 'item_reset'])
    new_sales_count = sum(1 for n in unread_notifs if n['type'] in ['sale', 'sale_refund', 'sale_delete'])
    new_restocks_count = sum(1 for n in unread_notifs if n['type'] in ['stock_in', 'stock_out'])
    new_admin_count = sum(1 for n in unread_notifs if n['type'] in ['user_added', 'user_updated', 'user_deleted', 'perms_update', 'settings_update', 'backup_import', 'data_purge'])
    
    # 2. Bulletins - filtered by branch
    bulletin_query = {"read_by": {"$ne": user_email}}
    if branch_id:
        bulletin_query["branch_id"] = branch_id
    unread_bulletins = get_notes_collection().count_documents(bulletin_query)
    
    # 3. Legend (Low Stock) - Keep logic but maybe user wants this persistent too? 
    # For now, keeping it based on last_views.legend
    user = get_users_collection().find_one({"email": user_email})
    last_views = user.get('last_views', {}) if user else {}
    lv_legend_str = last_views.get('legend')
    
    # Helper to parse aware dt (from our previous implementation)
    def parse_aware_dt(val):
        if not val: return None
        if isinstance(val, datetime):
            if val.tzinfo is None: return val.replace(tzinfo=timezone.utc)
            return val.astimezone(timezone.utc)
        try:
            return datetime.fromisoformat(str(val).replace('Z', '+00:00'))
        except: return None

    lv_legend = parse_aware_dt(lv_legend_str)
    
    item_query = {"active": {"$ne": False}}
    if branch_id:
        item_query["branch_id"] = branch_id
        
    items = list(get_items_collection().find(item_query))
    total_low_stock = 0
    new_low_stock_count = 0
    for item in items:
        metrics = calculate_item_metrics(item)
        if metrics['status_label'] in ['Low Stock', 'Out of Stock', 'Warning']:
            total_low_stock += 1
            u_dt = parse_aware_dt(item.get('updated_at') or item.get('created_at'))
            if not lv_legend or (u_dt and u_dt > lv_legend):
                new_low_stock_count += 1

    return jsonify({
        "unread_count": len(unread_notifs) + unread_bulletins,
        "sidebar": {
            "dashboard": new_sales_count + new_low_stock_count,
            "items": new_items_count,
            "sales": new_sales_count,
            "restocks": new_restocks_count,
            "sales_summary": 0,
            "legend": new_low_stock_count,
            "bulletins": unread_bulletins,
            "settings": new_admin_count
        },
        "notifications": [
            {
                "id": str(n['_id']),
                "type": n['type'],
                "title": n.get('title') or 'System Alert',
                "message": n.get('message') or 'No details available.',
                "priority": n.get('priority', 'INFO'),
                "user": n.get('author', 'System'),
                "created_at": n['created_at'].isoformat() if isinstance(n['created_at'], datetime) else n['created_at']
            } for n in unread_notifs[:15] # Increased to 15 recent
        ]
    })

@system_bp.route('/api/notifications/mark-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    user_email = session.get('email')
    now = datetime.now(timezone.utc)
    branch_id = session.get('branch_id')
    
    # 1. Mark Bulletins
    bulletin_q = {"read_by": {"$ne": user_email}}
    if branch_id:
        bulletin_q["branch_id"] = branch_id
    get_notes_collection().update_many(bulletin_q, {"$addToSet": {"read_by": user_email}})
    
    # 2. Mark Persistent Notifications
    notif_q = {"read_by": {"$ne": user_email}}
    if branch_id:
        notif_q["branch_id"] = branch_id
    get_notifications_collection().update_many(notif_q, {"$addToSet": {"read_by": user_email}})
    
    # 3. Reset Legend Timestamp
    get_users_collection().update_one({"email": user_email}, {"$set": {"last_views.legend": now}})
    
    from extensions import socketio
    socketio.emit('dashboard_update')
    
    return jsonify({"success": True})

@system_bp.route('/api/notifications/mark-one', methods=['POST'])
@login_required
def mark_one_notification_read():
    user_email = session.get('email')
    data = request.get_json()
    note_id = data.get('note_id')
    notif_id = data.get('notif_id')
    
    if note_id:
        get_notes_collection().update_one({"_id": ObjectId(note_id)}, {"$addToSet": {"read_by": user_email}})
    if notif_id:
        get_notifications_collection().update_one({"_id": ObjectId(notif_id)}, {"$addToSet": {"read_by": user_email}})
        
    from extensions import socketio
    socketio.emit('dashboard_update')
        
    return jsonify({"success": True})

@system_bp.route('/api/push-subscribe', methods=['POST'])
@login_required
def push_subscribe():
    subscription_info = request.get_json()
    if not subscription_info:
        return jsonify({"success": False, "error": "No subscription data"}), 400
        
    user_email = session.get('email')
    get_users_collection().update_one(
        {"email": user_email},
        {"$addToSet": {"push_subscriptions": subscription_info}}
    )
    return jsonify({"success": True})

@system_bp.route('/api/push-unsubscribe', methods=['POST'])
@login_required
def push_unsubscribe():
    data = request.get_json()
    endpoint = data.get('endpoint')
    if not endpoint:
        return jsonify({"success": False, "error": "No endpoint"}), 400
        
    user_email = session.get('email')
    # Remove the subscription matching this endpoint
    get_users_collection().update_one(
        {"email": user_email},
        {"$pull": {"push_subscriptions": {"endpoint": endpoint}}}
    )
    return jsonify({"success": True})

# --- System Info & Stats (Keeping existing boilerplate) ---
@system_bp.route('/system-info')
@login_required
def system_info():
    cpu = psutil.cpu_percent(interval=None); ram = psutil.virtual_memory(); disk = psutil.disk_usage('/')
    try: public_ip = requests.get('https://api.ipify.org', timeout=1).text
    except: public_ip = "Offline"
    local_ip = socket.gethostbyname(socket.gethostname())
    return jsonify({
        "cpu": cpu, "ram_percent": ram.percent, "ram_used": f"{ram.used / (1024**3):.1f} GB",
        "ram_total": f"{ram.total / (1024**3):.1f} GB", "disk_percent": disk.percent,
        "disk_free": f"{disk.free / (1024**3):.1f} GB", "public_ip": public_ip,
        "local_ip": local_ip, "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}", "python_v": platform.python_version()
    })

@system_bp.route('/admin/database-stats')
@login_required
def database_stats():
    from core.db import get_db; from extensions import mongo
    try:
        db = get_db(); stats = db.command("dbStats")
        def fb(s):
            for u in ['B','KB','MB','GB']:
                if s < 1024: return f"{s:.1f} {u}"
                s /= 1024
            return f"{s:.1f} TB"
        colls = [{"name": c, "count": db[c].count_documents({})} for c in db.list_collection_names()]
        return jsonify({
            "status": "Connected", "data_size": fb(stats.get('dataSize', 0)),
            "storage_size": fb(stats.get('storageSize', 0)), "index_size": fb(stats.get('indexSize', 0)),
            "collections_count": stats.get('collections', 0), "objects_count": stats.get('objects', 0),
            "avg_obj_size": fb(stats.get('avgObjSize', 0)), "db_name": db.name,
            "connection_host": f"{mongo.cx.address[0]}:{mongo.cx.address[1]}" if mongo.cx.address else "Localhost",
            "server_version": mongo.cx.server_info().get('version', 'Unknown'),
            "cluster_type": "Standalone/ReplicaSet", "collections": colls
        })
    except Exception as e: return jsonify({"status": "Disconnected", "error": str(e)})

@system_bp.route('/latest-log')
@login_required
def latest_log():
    log = get_system_log_collection().find_one(sort=[("timestamp", -1)])
    if log: return jsonify({"action": log.get('action'), "details": log.get('details'), "timestamp": log.get('timestamp')})
    return jsonify({"action": "N/A", "details": "No logs found.", "timestamp": ""})
