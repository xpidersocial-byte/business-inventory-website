import os
import json
import smtplib
import requests
import socket
import platform
from datetime import datetime
from email.mime.text import MIMEText
from pywebpush import webpush, WebPushException
from flask import session, request
from extensions import socketio
from core.db import get_settings_collection, get_subscriptions_collection, get_system_log_collection, get_menus_collection, get_notifications_collection, get_items_collection
from bson.objectid import ObjectId
from flask.json.provider import DefaultJSONProvider
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

# Password Security Helpers
def safe_object_id(oid):
    if not oid:
        return None
    try:
        return ObjectId(oid)
    except:
        return None

def hash_password(password):
    return generate_password_hash(password)

def verify_password(hashed_password, plain_password):
    if not hashed_password or not plain_password:
        return False
    # Legacy support: check if it's plain text (not starting with scrypt: or pbkdf2:)
    if not (hashed_password.startswith('scrypt:') or hashed_password.startswith('pbkdf2:')):
        return hashed_password == plain_password
    return check_password_hash(hashed_password, plain_password)

class MongoJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

def get_site_config():
    _defaults = {
        "type": "general",
        "business_name": "FBIHM Inventory",
        "business_icon": "bi-box-seam",
        "currency_symbol": "₱",
        "footer_text": "© 2026 Inventory Management System v2.0",
        "contact_address": "",
        "contact_phone": "",
        "contact_email": "admin@inventory.com",
        "timezone": "UTC",
        "date_format": "%Y-%m-%d",
        "time_format": "%I:%M:%S %p",
        "maintenance_mode": False,
        "low_stock_threshold": 5,
        "tax_rate": 0.0,
        "social_facebook": "",
        "social_twitter": "",
        "social_instagram": "",
        "custom_head_scripts": "",
        "custom_body_scripts": "",
        "login_background": "images/login_hero.webp",
        "default_theme": "facebook",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_password": "",
        "smtp_sender": "",
        "smtp_use_tls": True,
        "smtp_use_ssl": False,
        "email_notif_stock_in": True,
        "email_notif_stock_out": True,
        "email_notif_low_stock": True,
        "email_notif_sales": True,
        "email_notif_login": True,
        "email_notif_profile": True,
        "email_notif_inventory": True,
        "email_notif_bulletin": True,
        "email_recipient_list": "",
        "email_daily_summary": False,
        "email_weekly_summary": False,
        "email_monthly_summary": False,
        "email_yearly_summary": False,
        "email_daily_hour": 11,
        "email_daily_ampm": "PM",
        "email_weekly_hour": 11,
        "email_weekly_ampm": "PM",
        "email_monthly_hour": 11,
        "email_monthly_ampm": "PM",
        "email_yearly_hour": 11,
        "email_yearly_ampm": "PM",
        "updated_at": datetime.now()
    }
    try:
        settings_collection = get_settings_collection()
        config = settings_collection.find_one({"type": "general"})
        if not config:
            settings_collection.insert_one(_defaults.copy())
            config = _defaults
        if 'default_theme' not in config:
            config['default_theme'] = 'facebook'
            settings_collection.update_one({"type": "general"}, {"$set": {"default_theme": "facebook"}})
        return config
    except Exception as e:
        print(f"[DB-WARNING] Could not reach MongoDB, using defaults: {e}")
        return _defaults


def send_deployment_telemetry():
    """Sends server information to a configured webhook URL on startup."""
    webhook_url = os.getenv("TELEMETRY_WEBHOOK_URL")
    if not webhook_url:
        return

    try:
        # Gather basic server info
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        # Try to get public IP
        try:
            public_ip = requests.get('https://api.ipify.org', timeout=3).text
        except:
            public_ip = "Unknown"

        data = {
            "event": "SERVER_STARTUP",
            "business_name": get_site_config().get('business_name'),
            "timestamp": datetime.now().isoformat(),
            "hostname": hostname,
            "public_ip": public_ip,
            "local_ip": local_ip,
            "platform": platform.system(),
            "os_release": platform.release(),
            "python_version": platform.python_version()
        }

        requests.post(webhook_url, json=data, timeout=5)
        print(f"DEBUG: Telemetry sent to {webhook_url}")
    except Exception as e:
        print(f"DEBUG: Telemetry failed: {str(e)}")

def send_push_notification(title, body, target_emails=None):
    from core.db import get_users_collection
    users_collection = get_users_collection()
    
    query = {"push_subscriptions": {"$exists": True, "$not": {"$size": 0}}}
    if target_emails:
        query["email"] = {"$in": target_emails}
        
    users = list(users_collection.find(query))
    
    config = get_site_config()
    vapid_private = os.getenv("VAPID_PRIVATE_KEY") or config.get('vapid_private_key')
    vapid_email = os.getenv("VAPID_CLAIM_EMAIL") or config.get('vapid_claim_email', 'admin@inventory.com')
    
    if not vapid_private:
        return

    vapid_claims = {"sub": f"mailto:{vapid_email}"}
    
    for user in users:
        # Check user notification preferences if needed
        preferences = user.get('notification_preferences', {})
        if title.startswith('FBIHM Alert:') and not preferences.get('device_notifications_enabled', True):
            continue
            
        subscriptions = user.get('push_subscriptions', [])
        valid_subscriptions = []
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info=sub,
                    data=json.dumps({"title": title, "body": body, "url": "/"}),
                    vapid_private_key=vapid_private,
                    vapid_claims=vapid_claims
                )
                valid_subscriptions.append(sub)
            except WebPushException as ex:
                if ex.response and ex.response.status_code == 410:
                    pass # Skip adding to valid_subscriptions to drop this endpoint
                else:
                    valid_subscriptions.append(sub)
            except Exception:
                valid_subscriptions.append(sub)
                
        if len(valid_subscriptions) != len(subscriptions):
            users_collection.update_one({"_id": user['_id']}, {"$set": {"push_subscriptions": valid_subscriptions}})

def send_email_notification(subject, body, notif_type=None, override_recipient=None):
    config = get_site_config()
    
    if not notif_type or config.get(f"email_notif_{notif_type}", True):
        host = config.get('smtp_host')
        port = config.get('smtp_port', 587)
        user = config.get('smtp_user')
        passw = config.get('smtp_password')
        sender = config.get('smtp_sender') or user
        
        if override_recipient:
            recipients = [override_recipient]
        else:
            primary_recipient = config.get('contact_email')
            extra_recipients = config.get('email_recipient_list', '').split(',')
            recipients = [r.strip() for r in [primary_recipient] + extra_recipients if r.strip()]

        if not all([host, user, passw]) or not recipients:
            return False

        try:
            msg = MIMEText(body, 'plain', 'utf-8')
            msg['Subject'] = f"FBIHM Alert: {subject}"
            msg['From'] = f"{config.get('business_name', 'FBIHM')} <{sender}>"
            msg['To'] = ", ".join(recipients)

            use_tls = config.get('smtp_use_tls', True)
            use_ssl = config.get('smtp_use_ssl', False)

            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, timeout=10)
            else:
                server = smtplib.SMTP(host, port, timeout=10)
                if use_tls:
                    server.starttls()
            
            server.login(user, passw)
            server.send_message(msg)
            server.quit()
            return True
        except Exception as e:
            print(f"[SMTP-ERROR] {str(e)}")
            return False

def log_action(action_type, details, send_push=False):
    system_log_collection = get_system_log_collection()
    timestamp = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
    
    ip_addr = "System"
    try:
        if request.headers.get('X-Forwarded-For'):
            ip_addr = request.headers.get('X-Forwarded-For').split(',')[0]
        else:
            ip_addr = request.remote_addr
    except:
        pass

    system_log_collection.insert_one({
        "email": session.get('email', 'System'),
        "role": session.get('role', 'N/A'),
        "branch_id": safe_object_id(session.get('branch_id')),
        "action": action_type,
        "details": details,
        "timestamp": timestamp,
        "ip": ip_addr
    })
    
    if send_push:
        send_push_notification(f"FBIHM: {action_type}", f"{details} by {session.get('email', 'System')}")
    
    socketio.emit('system_update', {
        'action': action_type,
        'email': session.get('email', 'System'),
        'details': details,
        'timestamp': timestamp
    })

def trigger_notification(notif_type, title, message, data=None, priority='INFO'):
    """
    Professional notification engine for DB persistence and real-time SocketIO emission.
    Supports Priority: INFO, SUCCESS, WARNING, CRITICAL
    """
    notif_col = get_notifications_collection()
    now = datetime.now(timezone.utc)
    
    notif_doc = {
        "type": notif_type,
        "title": title,
        "message": message,
        "priority": priority,
        "author": session.get('email', 'System'),
        "branch_id": safe_object_id(session.get('branch_id')),
        "created_at": now,
        "read_by": [],
        "metadata": data or {}
    }
    
    try:
        res = notif_col.insert_one(notif_doc)
        notif_id = str(res.inserted_id)
    except Exception as e:
        print(f"[NOTIF-ERROR] DB insert failed: {e}")
        notif_id = None
        
    # Real-time Broadcast
    payload = {
        'id': notif_id,
        'type': notif_type,
        'title': title,
        'message': message,
        'priority': priority,
        'user': session.get('email', 'System'),
        'data': data,
        'timestamp': now.isoformat()
    }
    
    # Broadcast to all
    socketio.emit('system_notification', payload)
    
    # Also trigger generic dashboard update to refresh counts
    socketio.emit('dashboard_update')
    
    return notif_id

def calculate_item_metrics(item):
    cost = item.get('cost_price', 0)
    retail = item.get('retail_price', 0)
    stock = item.get('stock', 0)
    sold = item.get('sold', 0)
    lost = item.get('inventory_lost', 0)
    
    # Accurate metrics including losses
    inv_in = item.get('inventory_in', stock + sold + lost)
    inv_out = item.get('inventory_out', sold) + lost
    menu_name = item.get('menu', None)

    profit_per_unit = retail - cost
    total_revenue = retail * sold
    # Profit is revenue minus cost of sold items, MINUS cost of lost items
    total_profit = (profit_per_unit * sold) - (lost * cost)

    margin = (profit_per_unit / cost * 100) if cost > 0 else 0
    # Current asset value is what we have in stock
    inventory_value = cost * stock

    site_config = get_site_config()
    global_warning = site_config.get('warning_threshold', 10)
    global_low = site_config.get('low_stock_threshold', 5)

    warning_threshold = global_warning
    low_threshold = global_low

    if menu_name != None:
        menus_collection = get_menus_collection()
        menu_doc = menus_collection.find_one({"name": menu_name})
        if menu_doc:
            warning_threshold = menu_doc.get('warning_threshold', global_warning)
            low_threshold = menu_doc.get('low_stock_threshold', global_low)

    status_label = "In Stock"
    status_color = "success"
    
    if stock == 0:
        status_label = "Out of Stock"
        status_color = "danger"
    elif stock <= low_threshold:
        status_label = "Low Stock"
        status_color = "warning"
    elif stock <= warning_threshold:
        status_label = "Warning"
        status_color = "info"

    # Calculate days dormant
    updated_at = item.get('updated_at')
    days_dormant = 0
    if updated_at:
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            except:
                updated_at = None
        
        if updated_at:
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = now - updated_at
            days_dormant = delta.days

    return {
        **item,
        "sold": sold,
        "lost": lost,
        "stock": stock,
        "profit": profit_per_unit,
        "margin": round(margin, 2),
        "total_profit": total_profit,
        "total_revenue": total_revenue,
        "inventory_value": inventory_value,
        "inventory_in": inv_in,
        "inventory_out": inv_out,
        "status_label": status_label,
        "status_color": status_color,
        "warning_threshold": warning_threshold,
        "low_threshold": low_threshold,
        "days_dormant": days_dormant
    }

def update_item_stock(item_id, qty_change, action_type="OUT", reason="Sale"):
    """
    Centralized stock management with automatic notification triggering.
    qty_change: positive number
    action_type: 'IN' or 'OUT'
    """
    items_collection = get_items_collection()
    item = items_collection.find_one({"_id": ObjectId(item_id)})
    if not item:
        return False, "Item not found"

    old_stock = item.get('stock', 0)
    
    if action_type == "OUT":
        if old_stock < qty_change:
            return False, f"Insufficient stock for {item['name']}"
        new_stock = old_stock - qty_change
        
        # Determine increment fields based on reason
        inc_data = {"stock": -qty_change}
        if reason == "Sale":
            inc_data["sold"] = qty_change
            inc_data["inventory_out"] = qty_change
        else:
            # For Damages/Loss, increment a specific lost field
            inc_data["inventory_lost"] = qty_change
            
        update_query = {
            "$inc": inc_data,
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }
    else:
        new_stock = old_stock + qty_change
        update_query = {
            "$inc": {"stock": qty_change, "inventory_in": qty_change},
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }

    items_collection.update_one({"_id": ObjectId(item_id)}, update_query)
    
    # Notification Logic
    site_config = get_site_config()
    low_threshold = item.get('low_threshold')
    if low_threshold is None:
        # Check menu threshold or global
        menu_name = item.get('menu')
        if menu_name:
            menu_doc = get_menus_collection().find_one({"name": menu_name})
            low_threshold = menu_doc.get('low_stock_threshold') if menu_doc else None
    
    if low_threshold is None:
        low_threshold = site_config.get('low_stock_threshold', 5)

    if action_type == "OUT":
        if new_stock == 0 or new_stock <= low_threshold:
            # Determine targets: Owners + Cashiers of the branch
            from core.db import get_users_collection
            u_col = get_users_collection()
            branch_id_str = str(item.get('branch_id', ''))
            
            targets = list(u_col.find({
                "$or": [
                    {"role": "owner"},
                    {"role": "cashier", "branch_id": branch_id_str}
                ]
            }))
            
            # Only send push to users who have low_stock_alerts enabled (default: True)
            target_emails = [
                u['email'] for u in targets
                if 'email' in u and u.get('notification_preferences', {}).get('low_stock_alerts', True)
            ]
            
            if new_stock == 0:
                trigger_notification(
                    "stock_alert",
                    "Out of Stock!",
                    f"Item '{item['name']}' is now OUT OF STOCK.",
                    {"item_id": str(item_id), "stock": 0},
                    priority="CRITICAL"
                )
                if target_emails:
                    send_push_notification("FBIHM Alert: Out of Stock!", f"Item '{item['name']}' is now OUT OF STOCK.", target_emails)
                send_email_notification("Out of Stock Alert", f"Item '{item['name']}' is now out of stock.", notif_type="low_stock")
            elif new_stock <= low_threshold:
                trigger_notification(
                    "stock_alert",
                    "Low Stock Warning",
                    f"Item '{item['name']}' is running low ({new_stock} left).",
                    {"item_id": str(item_id), "stock": new_stock},
                    priority="WARNING"
                )
                if target_emails:
                    send_push_notification("FBIHM Alert: Low Stock", f"Item '{item['name']}' is running low ({new_stock} left).", target_emails)
                send_email_notification("Low Stock Alert", f"Item '{item['name']}' is low ({new_stock} left).", notif_type="low_stock")

    socketio.emit('dashboard_update')
    return True, "Stock updated"

def generate_sales_summary(period="Daily"):
    """
    Generates a periodic sales summary and pushes it to all system operators who opted in.
    """
    from core.db import get_users_collection, get_items_collection
    from flask import current_app
    from datetime import datetime, timezone, timedelta
    
    # Calculate time ranges
    now = datetime.now(timezone.utc)
    if period == "Daily":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "Weekly":
        start_date = now - timedelta(days=7)
    elif period == "Monthly":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "Yearly":
        start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = now - timedelta(days=1)
        
    items_col = get_items_collection()
    
    # We simulate reading from sales by evaluating sold metrics 
    # (Since FBIHM currently aggregates directly on items, we'll fetch high sold items updated recently)
    # A complete query would use the `sales` ledger collection for exact timeframes.
    try:
        from core.db import get_sales_collection
        sales = list(get_sales_collection().find({"created_at": {"$gte": start_date}}))
        total_revenue = sum([s.get('total', 0) for s in sales])
        total_items = sum([sum([i.get('quantity', 0) for i in s.get('items', [])]) for s in sales])
        
        # Determine top item
        item_counts = {}
        for s in sales:
            for item in s.get('items', []):
                item_counts[item.get('name', 'Unknown')] = item_counts.get(item.get('name', 'Unknown'), 0) + item.get('quantity', 0)
        top_item = max(item_counts, key=item_counts.get) if item_counts else "None"
        
        body = f"₱{total_revenue:,.2f} Revenue | {total_items} items sold. Top Item: {top_item}."
    except Exception as e:
        body = f"Your {period.lower()} sales and inventory performance summary is ready to be viewed."
        
    title = f"FBIHM Alert: {period} Sales Summary"
    
    # Get users who should receive this
    # Owners generally, but we consult their personal preferences
    users = list(get_users_collection().find({"role": "owner"}))
    target_emails = []
    
    pref_key = f"{period.lower()}_summary"
    for u in users:
        prefs = u.get("notification_preferences", {})
        # Default True if they haven't explicitly set it to false
        if prefs.get(pref_key, True):
            if 'email' in u:
                target_emails.append(u['email'])
    
    # Check global config for site-wide summary
    config = get_site_config()
    global_pref_key = f"email_{period.lower()}_summary"
    if config.get(global_pref_key, False):
        recipient_list = config.get('email_recipient_list', '')
        if recipient_list:
            for r in recipient_list.split(','):
                r = r.strip()
                if r and r not in target_emails:
                    target_emails.append(r)

    if target_emails:
        send_push_notification(title, body, target_emails)
        send_email_notification(f"{period} Sales Summary", body, override_recipient=",".join(target_emails))

def reschedule_periodic_jobs(scheduler):
    """
    Reads the latest site_config and updates the BackgroundScheduler jobs.
    """
    config = get_site_config()
    
    def to_24h(hour, ampm):
        h = int(hour)
        if ampm == 'PM' and h != 12: h += 12
        elif ampm == 'AM' and h == 12: h = 0
        return h

    mapping = {
        'Daily': {
            'id': 'daily_summary',
            'enabled': config.get('email_daily_summary', False),
            'hour': to_24h(config.get('email_daily_hour', 11), config.get('email_daily_ampm', 'PM')),
            'cron_params': {}
        },
        'Weekly': {
            'id': 'weekly_summary',
            'enabled': config.get('email_weekly_summary', False),
            'hour': to_24h(config.get('email_weekly_hour', 11), config.get('email_weekly_ampm', 'PM')),
            'cron_params': {'day_of_week': 'sun'}
        },
        'Monthly': {
            'id': 'monthly_summary',
            'enabled': config.get('email_monthly_summary', False),
            'hour': to_24h(config.get('email_monthly_hour', 11), config.get('email_monthly_ampm', 'PM')),
            'cron_params': {'day': 'last'}
        },
        'Yearly': {
            'id': 'yearly_summary',
            'enabled': config.get('email_yearly_summary', False),
            'hour': to_24h(config.get('email_yearly_hour', 11), config.get('email_yearly_ampm', 'PM')),
            'cron_params': {'month': 12, 'day': 31}
        }
    }

    for period, data in mapping.items():
        # Remove existing if any
        try:
            scheduler.remove_job(data['id'])
        except:
            pass
            
        if data['enabled']:
            scheduler.add_job(
                lambda p=period: generate_sales_summary(p),
                'cron',
                id=data['id'],
                hour=data['hour'],
                minute=0,
                **data['cron_params']
            )
            print(f"DEBUG: Rescheduled {period} summary for hour {data['hour']} (enabled: {data['enabled']})")
