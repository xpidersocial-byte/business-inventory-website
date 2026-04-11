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
from core.db import get_settings_collection, get_subscriptions_collection, get_system_log_collection, get_menus_collection
from bson.objectid import ObjectId
from flask.json.provider import DefaultJSONProvider

def parse_timestamp(value):
    """Safely parse various datetime string formats into a datetime object."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Prioritize ISO format for performance
        for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %I:%M:%S %p', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %I:%M %p']:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None

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

def send_push_notification(title, body):
    subscriptions_collection = get_subscriptions_collection()
    subscriptions = list(subscriptions_collection.find())
    
    # Check for VAPID keys in environment or site_config
    config = get_site_config()
    vapid_private = os.getenv("VAPID_PRIVATE_KEY") or config.get('vapid_private_key')
    vapid_email = os.getenv("VAPID_CLAIM_EMAIL") or config.get('vapid_claim_email', 'admin@inventory.com')
    
    if not vapid_private:
        # Silently fail if push not configured
        return

    vapid_claims = {"sub": f"mailto:{vapid_email}"}
    
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub['subscription_json'],
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=vapid_private,
                vapid_claims=vapid_claims
            )
        except WebPushException as ex:
            if ex.response and ex.response.status_code == 410:
                subscriptions_collection.delete_one({"_id": sub['_id']})
        except Exception:
            pass

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

def log_action(action_type, details, send_push=True):
    system_log_collection = get_system_log_collection()
    timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    
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

def calculate_item_metrics(item):
    cost = item.get('cost_price', 0)
    retail = item.get('retail_price', 0)
    stock = item.get('stock', 0)
    sold = item.get('sold', 0)
    inv_in = item.get('inventory_in', stock + sold)
    inv_out = item.get('inventory_out', sold)
    menu_name = item.get('menu', None)

    profit = abs(retail - cost)
    total_revenue = retail * sold
    total_profit = profit * sold

    margin = (profit / cost * 100) if cost > 0 else 0
    inventory_value = cost * (stock + sold)

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

    return {
        **item,
        "profit": profit,
        "margin": round(margin, 2),
        "total_profit": total_profit,
        "total_revenue": total_revenue,
        "inventory_value": inventory_value,
        "inventory_in": inv_in,
        "inventory_out": inv_out,
        "status_label": status_label,
        "status_color": status_color,
        "warning_threshold": warning_threshold,
        "low_threshold": low_threshold
    }
