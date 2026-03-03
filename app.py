import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
from werkzeug.utils import secure_filename
import os
import json
import psutil
import smtplib
import random
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from dotenv import load_dotenv
from bson.objectid import ObjectId
from flask_pymongo import PyMongo
from flask_socketio import SocketIO, emit
from functools import wraps
import ai_engine
import subprocess

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# Custom JSON Encoder for MongoDB/Datetime objects
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

app.json_encoder = MongoJSONEncoder

# SocketIO for Real-time Updates
socketio = SocketIO(app, 
                    cors_allowed_origins="*", 
                    async_mode='eventlet', 
                    engineio_logger=True, 
                    logger=True,
                    ping_timeout=120,
                    ping_interval=25,
                    allow_upgrades=True)

# MongoDB Configuration
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/flask_todo_db")
mongo = PyMongo(app)

# Collections
todos_collection = mongo.db.todos
users_collection = mongo.db.users
items_collection = mongo.db.items
purchase_collection = mongo.db.purchase
sales_collection = mongo.db.sales
inventory_log_collection = mongo.db.inventory_log
system_log_collection = mongo.db.system_logs
categories_collection = mongo.db.categories
notes_collection = mongo.db.notes
subscriptions_collection = mongo.db.subscriptions
dev_updates_collection = mongo.db.dev_updates
settings_collection = mongo.db.settings

# --- SITE CONFIG HELPER ---
def get_site_config():
    config = settings_collection.find_one({"type": "general"})
    if not config:
        # Default configuration
        config = {
            "type": "general",
            "business_name": "XPIDER Inventory",
            "business_icon": "bi-box-seam",
            "currency_symbol": "₱",
            "footer_text": "© 2026 Inventory Management System v2.0",
            
            # --- NEW EXTENDED SETTINGS ---
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
            
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_password": "",
            "smtp_sender": "",
            "smtp_use_tls": True,
            "smtp_use_ssl": False,
            
            # --- EMAIL NOTIFICATION LOGIC ---
            "email_notif_stock_in": True,
            "email_notif_stock_out": True,
            "email_notif_low_stock": True,
            "email_notif_sales": True,
            "email_recipient_list": "", # Comma-separated extra recipients
            
            "updated_at": datetime.now()
        }
        settings_collection.insert_one(config)
    return config

@app.context_processor
def inject_site_config():
    return dict(site_config=get_site_config())

# --- Web Push Helpers ---
from pywebpush import webpush, WebPushException

def send_push_notification(title, body):
    subscriptions = list(subscriptions_collection.find())
    vapid_private = os.getenv("VAPID_PRIVATE_KEY")
    vapid_claims = {"sub": f"mailto:{os.getenv('VAPID_CLAIM_EMAIL')}"}
    
    print(f"DEBUG: Attempting to send push to {len(subscriptions)} devices...")
    
    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub['subscription_json'],
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=vapid_private,
                vapid_claims=vapid_claims
            )
            print(f"DEBUG: Push sent successfully to {sub.get('email')}")
        except WebPushException as ex:
            if ex.response and ex.response.status_code == 410:
                # Subscription expired or removed - delete silently
                subscriptions_collection.delete_one({"_id": sub['_id']})
        except Exception as e:
            pass # Ignore all other errors to prevent spam

# --- SMTP Email Notification Helper ---
def send_email_notification(subject, body, notif_type=None, override_recipient=None):
    config = get_site_config()
    
    # Check if this notification type is enabled (unless overridden)
    if notif_type and not override_recipient:
        config_key = f"email_notif_{notif_type}"
        if not config.get(config_key, True):
            print(f"DEBUG: Notification '{notif_type}' is disabled in settings.")
            return False

    host = config.get('smtp_host')
    port = config.get('smtp_port', 587)
    user = config.get('smtp_user')
    passw = config.get('smtp_password')
    sender = config.get('smtp_sender') or user
    use_tls = config.get('smtp_use_tls', True)
    use_ssl = config.get('smtp_use_ssl', False)
    
    # Recipient List
    if override_recipient:
        recipients = [override_recipient]
    else:
        primary_recipient = config.get('contact_email')
        extra_recipients = config.get('email_recipient_list', '').split(',')
        recipients = [r.strip() for r in [primary_recipient] + extra_recipients if r.strip()]

    if not all([host, user, passw]) or not recipients:
        print("DEBUG: SMTP or Recipients not configured properly. Skipping email notification.")
        return False

    try:
        msg = MIMEText(body)
        msg['Subject'] = f"XPIDER Alert: {subject}"
        msg['From'] = sender
        msg['To'] = ", ".join(recipients)

        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
            server.ehlo()
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            server.ehlo()
            # Auto-enable TLS for port 587 or if explicitly requested
            if use_tls or port == 587:
                server.starttls()
                server.ehlo()
        
        server.login(user, passw)
        server.send_message(msg)
        server.quit()
        print(f"DEBUG: Email notification sent to {recipients}")
        return True
    except Exception as e:
        print(f"DEBUG: Failed to send email notification: {str(e)}")
        return False

# --- RBAC Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'email' not in session:
                return redirect(url_for('index'))
            
            user_role = session.get('role', 'cashier')
            if user_role == 'owner':
                return f(*args, **kwargs) # Owners always allowed
            
            # For cashiers, check dynamic permissions
            perms = get_cashier_permissions()
            endpoint = request.endpoint
            
            # Map endpoints to permission keys
            mapping = {
                'dashboard': 'dashboard',
                'items': 'items_master',
                'purchase': 'sales_ledger',
                'sales_summary': 'sales_summary',
                'inventory_io': 'inventory_io',
                'bulletin': 'bulletin_board',
                'developer_portal': 'developer_portal',
                'live_debug': 'live_debug',
                'health_scanner': 'health_scanner',
                'admin_accounts': 'admin_accounts',
                'general_setup': 'general_setup',
                'system_logs': 'system_logs'
            }
            
            perm_key = mapping.get(endpoint)
            if perm_key and not perms.get(perm_key, False):
                flash("Access Denied: The administrator has restricted this feature.", "danger")
                return redirect(url_for('dashboard'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_action(action_type, details, send_push=True):
    """Logs any user action to the database and optionally sends a push notification."""
    timestamp = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
    
    # Capture user IP address
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
    # Real-time Web Push (if enabled for this action)
    if send_push:
        send_push_notification(f"XPIDER: {action_type}", f"{details} by {session.get('email', 'System')}")
    
    # NEW: Real-time SocketIO Broadcast
    socketio.emit('system_update', {
        'action': action_type,
        'email': session.get('email', 'System'),
        'details': details,
        'timestamp': timestamp
    })

@app.route('/update-theme', methods=['POST'])
@login_required
def update_theme():
    theme = request.json.get('theme', 'default')
    email = session.get('email')
    
    # Save to user profile in DB
    users_collection.update_one(
        {"email": email},
        {"$set": {"theme": theme}}
    )
    
    # Update current session
    session['theme'] = theme
    
    # NEW: Broadcast theme change to all connected clients
    socketio.emit('theme_update', {'theme': theme})
    
    return jsonify({"success": True, "theme": theme})

@app.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    subscription_json = request.get_json()
    if not subscription_json:
        return jsonify({"success": False, "message": "Invalid subscription"}), 400
    
    # Store or update subscription
    subscriptions_collection.update_one(
        {"subscription_json.endpoint": subscription_json['endpoint']},
        {"$set": {"subscription_json": subscription_json, "email": session.get('email'), "updated_at": datetime.now()}},
        upsert=True
    )
    
    return jsonify({"success": True, "message": "Subscribed to push notifications!"})

@app.template_filter('format_datetime')
def format_datetime(value):
    if not value:
        return ""
    try:
        # Try to parse 24-hour format (which exists in older logs)
        dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%Y-%m-%d %I:%M:%S %p')
    except ValueError:
        try:
            # If already 12-hour or different, just return or re-format
            dt = datetime.strptime(value, '%Y-%m-%d %I:%M:%S %p')
            return dt.strftime('%Y-%m-%d %I:%M:%S %p')
        except ValueError:
            return value

def calculate_item_metrics(item):
    cost = item.get('cost_price', 0)
    retail = item.get('retail_price', 0)
    stock = item.get('stock', 0)
    sold = item.get('sold', 0)
    inv_in = item.get('inventory_in', stock + sold) 
    inv_out = item.get('inventory_out', sold)       

    # Algorithm Update: Profit is the absolute difference between Retail and Cost
    profit = abs(retail - cost)
    
    # Corrected: Only calculate profit and revenue for items actually SOLD
    total_revenue = retail * sold
    total_profit = profit * sold
    
    margin = (profit / cost * 100) if cost > 0 else 0
    # Total Inv Value remains (Stock + Sold) * Cost as per your previous request
    inventory_value = cost * (stock + sold)

    status = "In Stock"
    if stock == 0:
        status = "Out of Stock"
    elif stock < 20:
        status = "Low Stock"

    return {
        **item,
        "profit": profit,
        "margin": round(margin, 2),
        "total_profit": total_profit,
        "total_revenue": total_revenue,
        "inventory_value": inventory_value,
        "inventory_in": inv_in,
        "inventory_out": inv_out,
        "status": status
    }

@app.route('/')
def index():
    if 'email' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html', site_config=get_site_config())

@app.before_request
def maintenance_mode_check():
    """Check if system is in maintenance mode."""
    config = get_site_config()
    if config.get('maintenance_mode', False):
        # Exempt developer and login/static routes
        exempt_routes = ['login', 'index', 'static']
        if request.endpoint not in exempt_routes:
            return render_template('maintenance.html', config=config), 503

@app.before_request
def load_user_theme():
    """Source of truth for theme: always check the database if logged in."""
    if 'email' in session:
        # Fetch directly from DB to ensure sync across all devices
        user = users_collection.find_one({"email": session['email']}, {"theme": 1})
        if user:
            g.theme = user.get('theme', 'default')
            session['theme'] = g.theme

@app.after_request
def add_security_headers(response):
    """Inject standard security headers into every response."""
    # Updated CSP to allow socket.io and Google Drive Embedding
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.socket.io; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://placehold.co https://*.googleusercontent.com https://*.google.com; "
        "frame-src 'self' https://drive.google.com https://*.google.com; "
        "connect-src 'self' https://cdn.jsdelivr.net https://cdn.socket.io ws: wss:;"
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    user = users_collection.find_one({"email": email, "password": password})
    if user:
        session['email'] = email
        session['role'] = user.get('role', 'cashier')
        session['theme'] = user.get('theme', 'default') # Load theme into session
        log_action("LOGIN", f"User '{email}' logged in.")
        return redirect(url_for('dashboard'))
    else:
        log_action("LOGIN_FAILED", f"Failed login attempt for email: {email}")
        flash("Invalid email or password!", "danger")
        return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    raw_items = list(items_collection.find())
    
    # Fetch Dev Updates (Visible to dev only)
    dev_updates = list(dev_updates_collection.find().sort("timestamp", -1))
    
    # --- 1. Sales Velocity Algorithm ---
    # Fetch all sales logs to find the last sale date for each item
    sales_logs = list(inventory_log_collection.find({"type": "OUT"}))
    last_sale_map = {}
    for log in sales_logs:
        if 'item_name' in log and 'timestamp' in log:
            # Keep the most recent date
            current_date = log['timestamp']
            if log['item_name'] not in last_sale_map or current_date > last_sale_map[log['item_name']]:
                last_sale_map[log['item_name']] = current_date
    
    processed_items = [calculate_item_metrics(item) for item in raw_items]
    
    # Categorize Items
    cold_stock = []
    sporadic_stock = []
    now = datetime.now()
    
    for item in processed_items:
        last_sold_str = last_sale_map.get(item['name'])
        days_since_sale = 999 # Default to a high number if never sold
        
        if last_sold_str:
            try:
                last_sold_date = datetime.strptime(last_sold_str, '%Y-%m-%d %I:%M:%S %p')
                days_since_sale = (now - last_sold_date).days
            except ValueError:
                pass
        
        # Logic for "Cold Stock" (Not sold in 30 days OR never sold, but has stock)
        if item['stock'] > 0:
            if days_since_sale > 30:
                item['days_dormant'] = days_since_sale
                cold_stock.append(item)
            # Logic for "Sporadic" (Sold recently, but low total volume)
            elif days_since_sale <= 30 and item['sold'] < 5:
                item['last_sold'] = last_sold_str
                sporadic_stock.append(item)

    # Sort lists
    cold_stock = sorted(cold_stock, key=lambda x: x['stock'] * x['cost_price'], reverse=True)[:5] # High value stuck items first
    sporadic_stock = sorted(sporadic_stock, key=lambda x: x['sold'], reverse=True)[:5]

    # --- 2. Monthly Performance Analysis (Current Month) ---
    month_str = now.strftime('%Y-%m') # e.g. "2026-03"
    current_month_display = now.strftime('%B %Y')
    
    # Filter logs for current month and type OUT
    monthly_sales_logs = list(inventory_log_collection.find({
        "type": "OUT",
        "timestamp": {"$regex": f"^{month_str}"}
    }))
    
    # Aggregate monthly sales by item
    monthly_item_sales = {} # {item_name: {"qty": 0, "revenue": 0, "profit": 0}}
    
    # Create a quick map of item details for performance
    item_details_map = {item['name']: item for item in processed_items}
    
    for log in monthly_sales_logs:
        name = log.get('item_name')
        qty = log.get('qty', 0)
        if name in item_details_map:
            details = item_details_map[name]
            if name not in monthly_item_sales:
                monthly_item_sales[name] = {"qty": 0, "revenue": 0, "profit": 0, "name": name}
            
            monthly_item_sales[name]["qty"] += qty
            monthly_item_sales[name]["revenue"] += qty * details.get('retail_price', 0)
            monthly_item_sales[name]["profit"] += qty * (details.get('retail_price', 0) - details.get('cost_price', 0))

    # Calculate Star Performers (Top 5 by quantity sold this month)
    star_performers = sorted(monthly_item_sales.values(), key=lambda x: x['qty'], reverse=True)[:5]
    
    # Monthly aggregate metrics
    monthly_revenue = sum(x['revenue'] for x in monthly_item_sales.values())
    monthly_profit = sum(x['profit'] for x in monthly_item_sales.values())
    monthly_qty = sum(x['qty'] for x in monthly_item_sales.values())

    # --- Standard Metrics ---
    site_config = get_site_config()
    threshold = site_config.get('low_stock_threshold', 5)
    
    out_of_stock_items = [i for i in processed_items if i['stock'] <= 0]
    low_stock_items = [i for i in processed_items if 0 < i['stock'] < threshold]
    items_count = len(processed_items)
    stock_total = sum(item['stock'] for item in processed_items)
    total_inventory_value = sum(item['inventory_value'] for item in processed_items)
    total_revenue = sum(item['retail_price'] * item['sold'] for item in processed_items)
    total_profit = sum(item['total_profit'] for item in processed_items)
    total_quantity_sold = sum(item['sold'] for item in processed_items)
    
    top_item_name = star_performers[0]['name'] if star_performers else "N/A"
    
    # Prepare chart data (Top 5 for focused distribution chart)
    chart_data = sorted(monthly_item_sales.values(), key=lambda x: x['qty'], reverse=True)
    
    # Enrich chart labels with revenue information for "more useful info"
    chart_labels = []
    chart_values = []
    
    for x in chart_data[:5]:
        chart_labels.append(f"{x['name']} (₱{x['revenue']:,.0f})")
        chart_values.append(x['qty'])
    
    # Add "Others" to chart if applicable
    if len(chart_data) > 5:
        others_qty = sum(x['qty'] for x in chart_data[5:])
        others_rev = sum(x['revenue'] for x in chart_data[5:])
        chart_labels.append(f"Others (₱{others_rev:,.0f})")
        chart_values.append(others_qty)
    
    return render_template('dashboard.html', 
                           email=session['email'], 
                           role=session.get('role'), 
                           items_count=items_count, 
                           stock_total=stock_total, 
                           total_value=total_inventory_value, 
                           total_revenue=total_revenue, 
                           total_profit=total_profit, 
                           total_qty=total_quantity_sold,
                           monthly_revenue=monthly_revenue,
                           monthly_profit=monthly_profit,
                           monthly_qty=monthly_qty,
                           star_performers=star_performers,
                           top_item=top_item_name, 
                           current_month=current_month_display, 
                           chart_labels=chart_labels, 
                           chart_values=chart_values, 
                           out_of_stock_items=out_of_stock_items,
                           low_stock_items=low_stock_items,
                           cold_stock=cold_stock,
                           sporadic_stock=sporadic_stock,
                           dev_updates=dev_updates)

@app.route('/dev-updates/add', methods=['POST'])
@login_required
def add_dev_update():
    # Allowed for all roles
    pass
    
    content = request.form.get('content')
    tag = request.form.get('tag', 'UPDATE') # UPDATE, FEATURE, BUG, TODO
    
    if content:
        dev_updates_collection.insert_one({
            "content": content,
            "tag": tag,
            "timestamp": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
        })
        flash("Development update posted!", "success")
    return redirect(url_for('developer_portal'))

@app.route('/dev-updates/delete/<id>', methods=['POST'])
@login_required
def delete_dev_update(id):
    # All roles allowed
    pass
    
    dev_updates_collection.delete_one({"_id": ObjectId(id)})
    flash("Update removed.", "info")
    return redirect(url_for('developer_portal'))

@app.route('/items')
@login_required
def items():
    raw_items = list(items_collection.find())
    processed = [calculate_item_metrics(item) for item in raw_items]
    categories = list(categories_collection.find().sort("name", 1))
    
    site_config = get_site_config()
    threshold = site_config.get('low_stock_threshold', 5)
    
    return render_template('items.html', items=processed, role=session.get('role'), categories=categories, low_stock_threshold=threshold)

@app.route('/items/add', methods=['POST'])
@login_required
def add_item():
    # Allow both owner and cashier to add items
    name = request.form.get('name'); category = request.form.get('category')
    cost_price = float(request.form.get('cost_price', 0))
    retail_price = float(request.form.get('retail_price', 0))
    stock = int(request.form.get('stock', 0)); sold = int(request.form.get('sold', 0))
    if name:
        items_collection.insert_one({"name": name, "category": category, "cost_price": cost_price, "retail_price": retail_price, "stock": stock, "sold": sold})
        log_action("ADD_ITEM", f"Added: {name}")
        flash(f"Item '{name}' added!", "success")
    return redirect(url_for('items'))

@app.route('/items/edit/<id>', methods=['POST'])
@login_required
@role_required('owner')
def edit_item(id):
    name = request.form.get('name'); category = request.form.get('category')
    cost_price = float(request.form.get('cost_price', 0))
    retail_price = float(request.form.get('retail_price', 0))
    stock = int(request.form.get('stock', 0)); sold = int(request.form.get('sold', 0))
    if name:
        items_collection.update_one({'_id': ObjectId(id)}, {'$set': {"name": name, "category": category, "cost_price": cost_price, "retail_price": retail_price, "stock": stock, "sold": sold}})
        log_action("EDIT_ITEM", f"Updated: {name}")
        flash(f"Item '{name}' updated!", "success")
    return redirect(url_for('items'))

@app.route('/items/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_item(id):
    item = items_collection.find_one({'_id': ObjectId(id)})
    if item:
        items_collection.delete_one({'_id': ObjectId(id)})
        log_action("DELETE_ITEM", f"Deleted: {item['name']}")
        flash("Item deleted.", "info")
    return redirect(url_for('items'))

@app.route('/inventory-io')
@login_required
def inventory_io():
    logs = list(inventory_log_collection.find().sort("timestamp", -1))
    items_list = list(items_collection.find().sort("name", 1))
    return render_template('inventory_io.html', logs=logs, items=items_list, role=session.get('role'))

@app.route('/inventory/stock-in', methods=['POST'])
@login_required
def stock_in():
    item_id = request.form.get('item_id'); qty = int(request.form.get('qty', 0))
    if item_id and qty > 0:
        item = items_collection.find_one({"_id": ObjectId(item_id)})
        if item:
            items_collection.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": qty, "inventory_in": qty}})
            inventory_log_collection.insert_one({"item_name": item['name'], "type": "IN", "qty": qty, "user": session['email'], "timestamp": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')})
            log_action("STOCK_IN", f"In: {qty} x {item['name']}")
            
            # Send Email Alert
            send_email_notification(
                "Stock In Recorded",
                f"New stock added: {qty} units of '{item['name']}' by {session.get('email')}.",
                notif_type="stock_in"
            )
            
            flash(f"Stock IN recorded!", "success")
    return redirect(url_for('inventory_io'))

@app.route('/inventory/stock-out', methods=['POST'])
@login_required
def stock_out():
    item_id = request.form.get('item_id'); qty = int(request.form.get('qty', 0))
    if item_id and qty > 0:
        item = items_collection.find_one({"_id": ObjectId(item_id)})
        if item:
            if item.get('stock', 0) >= qty:
                new_stock = item['stock'] - qty
                items_collection.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": -qty, "sold": qty, "inventory_out": qty}})
                inventory_log_collection.insert_one({"item_name": item['name'], "type": "OUT", "qty": qty, "user": session['email'], "timestamp": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')})
                log_action("STOCK_OUT", f"Out: {qty} x {item['name']}")
                
                # Send Email Alert
                send_email_notification(
                    "Stock Out Recorded",
                    f"Stock reduction: {qty} units of '{item['name']}' removed by {session.get('email')}. Remaining stock: {new_stock}",
                    notif_type="stock_out"
                )
                
                # Check for Low Stock
                site_config = get_site_config()
                threshold = site_config.get('low_stock_threshold', 5)
                if 0 < new_stock <= threshold:
                    send_email_notification(
                        "Low Stock Alert!",
                        f"CRITICAL: Item '{item['name']}' is now in low stock. Only {new_stock} units left! (Threshold: {threshold})",
                        notif_type="low_stock"
                    )
                elif new_stock == 0:
                    send_email_notification(
                        "Out of Stock Alert!",
                        f"URGENT: Item '{item['name']}' is now OUT OF STOCK!",
                        notif_type="low_stock"
                    )

                flash(f"Stock OUT recorded!", "warning")
            else:
                flash("Insufficient stock!", "danger")
    return redirect(url_for('inventory_io'))

@app.route('/purchase')
@login_required
@role_required('owner')
def purchase():
    purchases = list(purchase_collection.find().sort("date", -1))
    items_list = list(items_collection.find().sort("name", 1))
    return render_template('purchase.html', purchases=purchases, items=items_list, role=session.get('role'))

@app.route('/purchase/add', methods=['POST'])
@login_required
@role_required('owner')
def add_purchase():
    item_id = request.form.get('item_id')
    qty = int(request.form.get('qty', 0))

    if item_id and qty > 0:
        item = items_collection.find_one({"_id": ObjectId(item_id)})
        if item:
            if item.get('stock', 0) >= qty:
                previous_stock = item.get('stock', 0)
                total_stock = previous_stock - qty
                unit_price = item.get('retail_price', 0)
                total = qty * unit_price

                purchase_doc = {
                    "date": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'),
                    "item_name": item['name'],
                    "qty": qty,
                    "previous_stock": previous_stock,
                    "total_stock": total_stock,
                    "unit_cost": unit_price,
                    "total": total,
                    "status": "Sold",
                    "user": session.get('email')
                }
                purchase_collection.insert_one(purchase_doc)

                # Update Item Stock and Sales metrics
                items_collection.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": -qty, "sold": qty, "inventory_out": qty}})
                inventory_log_collection.insert_one({
                    "item_name": item['name'],
                    "type": "OUT",
                    "qty": qty,
                    "user": session['email'],
                    "timestamp": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
                })

                log_action("SALE", f"Sold: {qty} x {item['name']} for ₱{total}")

                # Send Email Alert for Sale
                send_email_notification(
                    "New Sale Recorded",
                    f"A new sale was recorded: {qty} x '{item['name']}' for {total}. Sold by {session.get('email')}. Remaining stock: {total_stock}",
                    notif_type="sales"
                )

                # Check for Low Stock after sale
                site_config = get_site_config()
                threshold = site_config.get('low_stock_threshold', 5)
                if 0 < total_stock <= threshold:
                    send_email_notification(
                        "Low Stock Alert!",
                        f"CRITICAL: Item '{item['name']}' is now in low stock after a sale. Only {total_stock} units left! (Threshold: {threshold})",
                        notif_type="low_stock"
                    )
                elif total_stock == 0:
                    send_email_notification(
                        "Out of Stock Alert!",
                        f"URGENT: Item '{item['name']}' is now OUT OF STOCK following a sale!",
                        notif_type="low_stock"
                    )
                flash(f"Sale recorded! Stock deducted for {item['name']}.", "success")
            else:
                flash(f"Insufficient stock for {item['name']}!", "danger")
    return redirect(url_for('purchase'))
@app.route('/sales-summary')
@login_required
def sales_summary():
    view_type = request.args.get('view', 'yearly') # yearly, weekly, daily
    now = datetime.now()
    current_year = now.year

    # 1. Fetch all sales (STOCK_OUT) logs
    all_logs = list(inventory_log_collection.find({"type": "OUT"}))
    
    # 2. Fetch all items to get cost/retail prices for calculation
    items_by_name = {item['name']: item for item in items_collection.find()}

    # Initialize data structures
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_revenue = [0] * 12
    monthly_profit = [0] * 12

    # --- 1. Monthly Performance (Yearly Overview) ---
    for log in all_logs:
        try:
            log_date = datetime.strptime(log['timestamp'], '%Y-%m-%d %I:%M:%S %p')
            if log_date.year == current_year:
                item = items_by_name.get(log['item_name'])
                if item:
                    qty = log.get('qty', 0)
                    month_idx = log_date.month - 1
                    
                    # SALES = Actual Qty Sold * Retail Price
                    monthly_revenue[month_idx] += qty * item.get('retail_price', 0)
                    # PROFIT = Actual Qty Sold * |Retail - Cost|
                    profit_per_unit = abs(item.get('retail_price', 0) - item.get('cost_price', 0))
                    monthly_profit[month_idx] += qty * profit_per_unit
        except: continue

    # --- 2. Weekly Trend (Last 12 weeks) ---
    from datetime import timedelta
    weeks_labels = []
    weekly_revenue = []
    weekly_profit = []
    
    for i in range(11, -1, -1):
        start_date = now - timedelta(weeks=i+1)
        end_date = now - timedelta(weeks=i)
        weeks_labels.append(start_date.strftime('%-m/%-d/%y'))
        
        week_rev = 0
        week_prof = 0
        for log in all_logs:
            try:
                log_date = datetime.strptime(log['timestamp'], '%Y-%m-%d %I:%M:%S %p')
                if start_date <= log_date < end_date:
                    item = items_by_name.get(log['item_name'])
                    if item:
                        qty = log.get('qty', 0)
                        week_rev += qty * item.get('retail_price', 0)
                        profit_per_unit = abs(item.get('retail_price', 0) - item.get('cost_price', 0))
                        week_prof += qty * profit_per_unit
            except: continue
        
        weekly_revenue.append(week_rev)
        weekly_profit.append(week_prof)

    # --- 3. Daily Breakdown (Last 30 Days) ---
    daily_labels = []
    daily_revenue = []
    daily_profit = []
    for i in range(29, -1, -1):
        target_date = now - timedelta(days=i)
        daily_labels.append(target_date.strftime('%-m/%-d/%y'))
        
        day_rev = 0
        day_prof = 0
        for log in all_logs:
            try:
                log_date = datetime.strptime(log['timestamp'], '%Y-%m-%d %I:%M:%S %p')
                if log_date.date() == target_date.date():
                    item = items_by_name.get(log['item_name'])
                    if item:
                        qty = log.get('qty', 0)
                        day_rev += qty * item.get('retail_price', 0)
                        profit_per_unit = abs(item.get('retail_price', 0) - item.get('cost_price', 0))
                        day_prof += qty * profit_per_unit
            except: continue
                
        daily_revenue.append(day_rev)
        daily_profit.append(day_prof)

    # Calculate aggregate stats based on view_type
    if view_type == 'weekly':
        total_revenue = sum(weekly_revenue)
        total_profit = sum(weekly_profit)
        avg_label = "Avg. Weekly Revenue"
        total_label = "Total Weekly Profit"
        data_points = [r for r in weekly_revenue if r > 0]
        avg_revenue = total_revenue / len(data_points) if data_points else 0
    elif view_type == 'daily':
        total_revenue = sum(daily_revenue)
        total_profit = sum(daily_profit)
        avg_label = "Avg. Daily Revenue"
        total_label = "Total Daily Profit"
        data_points = [r for r in daily_revenue if r > 0]
        avg_revenue = total_revenue / len(data_points) if data_points else 0
    else: # yearly/monthly
        total_revenue = sum(monthly_revenue)
        total_profit = sum(monthly_profit)
        avg_label = "Avg. Monthly Revenue"
        total_label = "Total Annual Profit"
        data_points = [r for r in monthly_revenue if r > 0]
        avg_revenue = total_revenue / len(data_points) if data_points else 0

    avg_profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0

    return render_template('sales_summary.html', 
                           email=session['email'],
                           role=session.get('role'),
                           months_labels=months, 
                           revenue_values=monthly_revenue, 
                           profit_values=monthly_profit,
                           weeks_labels=weeks_labels, 
                           weekly_revenue=weekly_revenue,
                           weekly_profit_values=weekly_profit,
                           daily_labels=daily_labels,
                           daily_revenue=daily_revenue,
                           daily_profit_values=daily_profit,
                           avg_revenue=avg_revenue,
                           total_profit=total_profit,
                           avg_label=avg_label,
                           total_label=total_label,
                           avg_profit_margin=round(avg_profit_margin, 1),
                           view_type=view_type,
                           now=now)

@app.route('/system-logs')
@login_required
@role_required('owner')
def system_logs():
    logs = list(system_log_collection.find().sort("timestamp", -1).limit(100))
    return render_template('system_logs.html', logs=logs, role=session.get('role'))

@app.route('/ai-strategist')
@login_required
def ai_strategist():
    # Gather data context
    items_list = list(items_collection.find({}, {'_id': 0})) # No ObjectIds for AI context
    recent_logs = list(inventory_log_collection.find({"type": "OUT"}, {'_id': 0}).sort("timestamp", -1).limit(10))
    
    context_data = {
        "items": items_list,
        "recent_sales": recent_logs,
        "user_role": session.get('role', 'cashier')
    }
    
    ai_insight = ai_engine.get_ai_response("Analyze this business and provide 3-4 strategic bullets.", context_data=context_data)
    
    return render_template('ai_strategist.html', 
                           insight=ai_insight, 
                           role=session.get('role'))

# --- PERMISSIONS HELPER ---
def get_cashier_permissions():
    perms = settings_collection.find_one({"type": "cashier_permissions"})
    if not perms:
        # Default: Cashiers only see basic sales/inventory
        perms = {
            "type": "cashier_permissions",
            "dashboard": True,
            "items_master": True,
            "sales_ledger": True,
            "sales_summary": False,
            "inventory_io": True,
            "bulletin_board": True,
            "developer_portal": False,
            "live_debug": False,
            "health_scanner": False,
            "admin_accounts": False,
            "general_setup": False,
            "system_logs": False,
            
            # Setup Sections (Only if general_setup is true)
            "setup_identity": False,
            "setup_localization": False,
            "setup_logic": False,
            "setup_categories": True,
            "setup_advanced": False,
            "setup_assets": False,
            "setup_backup": False,
            "setup_danger_zone": False,
            "setup_smtp": False,
            "setup_notifications": False
        }
        settings_collection.insert_one(perms)
    return perms

@app.context_processor
def inject_permissions():
    return dict(cashier_perms=get_cashier_permissions())

@app.route('/admin/accounts')
@login_required
def admin_accounts():
    # Only Owners can manage permissions/accounts
    if session.get('role') != 'owner':
        flash("Access Denied.", "danger")
        return redirect(url_for('dashboard'))
        
    all_users = list(users_collection.find({}, {'password': 0}))
    return render_template('admin_accounts.html', 
                           users=all_users, 
                           perms=get_cashier_permissions(),
                           role=session.get('role'))

@app.route('/admin/permissions/update', methods=['POST'])
@login_required
@role_required('owner')
def update_permissions():
    fields = [
        "dashboard", "items_master", "sales_ledger", "sales_summary", 
        "inventory_io", "bulletin_board", "developer_portal", "live_debug", 
        "health_scanner", "admin_accounts", "general_setup", "system_logs",
        "setup_identity", "setup_localization", "setup_logic", "setup_users",
        "setup_categories", "setup_themes", "setup_advanced", "setup_assets", 
        "setup_backup", "setup_danger_zone", "setup_smtp", "setup_notifications"
    ]
    
    new_perms = {field: (request.form.get(field) == 'on') for field in fields}
    settings_collection.update_one({"type": "cashier_permissions"}, {"$set": new_perms}, upsert=True)
    
    log_action("UPDATE_PERMISSIONS", "Owner updated cashier access levels.")
    flash("Cashier permissions updated successfully!", "success")
    return redirect(url_for('admin_accounts'))

@app.route('/general-setup')
@login_required
@role_required('owner')
def general_setup():
    # 1. Tech Files for SEO Manager
    tech_files = {}
    for filename in ['robots.txt', 'sitemap.xml', 'manifest.json']:
        path = os.path.join(os.getcwd(), 'static', filename)
        try:
            with open(path, 'r') as f:
                tech_files[filename.replace('.', '_')] = f.read()
        except:
            tech_files[filename.replace('.', '_')] = ""

    # 3. Users and Categories (Merged from settings)
    all_users = list(users_collection.find({}, {'password': 0}))
    categories = list(categories_collection.find().sort("name", 1))

    return render_template('general_setup.html',
                           role=session.get('role'),
                           tech_files=tech_files,
                           users=all_users,
                           categories=categories)

@app.route('/settings')
@login_required
def settings():
    return redirect(url_for('admin_accounts'))
@app.route('/settings/profile/update', methods=['POST'])
@login_required
@role_required('owner')
def update_profile():
    # Helper to clean numbers
    def clean_num(val, default=0, is_int=False):
        if not val or str(val).strip() == "": return default
        try:
            return int(val) if is_int else float(val)
        except:
            return default

    # Extract all fields from form
    update_data = {
        "business_name": request.form.get('business_name', 'XPIDER Inventory'),
        "business_icon": request.form.get('business_icon', 'bi-box-seam'),
        "currency_symbol": request.form.get('currency_symbol', '₱'),
        "footer_text": request.form.get('footer_text', ''),
        
        "contact_address": request.form.get('contact_address', ''),
        "contact_phone": request.form.get('contact_phone', ''),
        "contact_email": request.form.get('contact_email', ''),
        
        "timezone": request.form.get('timezone', 'UTC'),
        "date_format": request.form.get('date_format', '%Y-%m-%d'),
        "time_format": request.form.get('time_format', '%I:%M:%S %p'),
        
        "maintenance_mode": request.form.get('maintenance_mode') == 'on',
        "low_stock_threshold": clean_num(request.form.get('low_stock_threshold'), 5, True),
        "tax_rate": clean_num(request.form.get('tax_rate'), 0.0),
        
        "social_facebook": request.form.get('social_facebook', ''),
        "social_twitter": request.form.get('social_twitter', ''),
        "social_instagram": request.form.get('social_instagram', ''),
        
        "custom_head_scripts": request.form.get('custom_head_scripts', ''),
        "custom_body_scripts": request.form.get('custom_body_scripts', ''),
        
        # --- SMTP SETTINGS ---
        "smtp_host": request.form.get('smtp_host', ''),
        "smtp_port": clean_num(request.form.get('smtp_port'), 587, True),
        "smtp_user": request.form.get('smtp_user', ''),
        "smtp_password": request.form.get('smtp_password', ''),
        "smtp_sender": request.form.get('smtp_sender', ''),
        "smtp_use_tls": request.form.get('smtp_use_tls') == 'on',
        "smtp_use_ssl": request.form.get('smtp_use_ssl') == 'on',
        
        # --- EMAIL NOTIFICATION LOGIC ---
        "email_notif_stock_in": request.form.get('email_notif_stock_in') == 'on',
        "email_notif_stock_out": request.form.get('email_notif_stock_out') == 'on',
        "email_notif_low_stock": request.form.get('email_notif_low_stock') == 'on',
        "email_notif_sales": request.form.get('email_notif_sales') == 'on',
        "email_recipient_list": request.form.get('email_recipient_list', ''),
        
        "updated_at": datetime.now()
    }
    
    settings_collection.update_one(
        {"type": "general"},
        {"$set": update_data},
        upsert=True
    )
    
    log_action("UPDATE_PROFILE", f"Updated comprehensive site configuration.")
    flash("Business Profile updated successfully!", "success")
    return redirect(url_for('general_setup'))

@app.route('/settings/login-bg/update', methods=['POST'])
@login_required
@role_required('owner')
def update_login_bg():
    if 'login_bg' not in request.files:
        flash("No file part", "danger")
        return redirect(url_for('admin_accounts'))
    
    file = request.files['login_bg']
    if file.filename == '':
        flash("No selected file", "danger")
        return redirect(url_for('admin_accounts'))
    
    if file:
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        new_filename = f"login_bg_{int(datetime.now().timestamp())}.{ext}"
        target_path = os.path.join(os.getcwd(), 'static', 'images', new_filename)
        file.save(target_path)
        
        # Update DB
        settings_collection.update_one(
            {"type": "general"},
            {"$set": {"login_background": f"images/{new_filename}"}}
        )
        
        log_action("UPDATE_LOGIN_BG", "Updated login page background image.")
        flash("Login background updated!", "success")
    
    return redirect(url_for('admin_accounts'))

@app.route('/settings/favicon/update', methods=['POST'])
@login_required
@role_required('owner')
def update_favicon():
    if 'favicon' not in request.files:
        flash("No file part", "danger")
        return redirect(url_for('admin_accounts'))
    
    file = request.files['favicon']
    if file.filename == '':
        flash("No selected file", "danger")
        return redirect(url_for('admin_accounts'))
    
    if file:
        # Save as static/favicon.ico regardless of original name
        # (Though we might want to support PNG/GIF, favicon.ico is standard)
        target_path = os.path.join(os.getcwd(), 'static', 'favicon.ico')
        file.save(target_path)
        
        log_action("UPDATE_FAVICON", "Updated website favicon.")
        flash("Favicon updated successfully!", "success")
    
    return redirect(url_for('admin_accounts'))

@app.route('/settings/backup/download')
@login_required
@role_required('owner')
def download_backup():
    """Generates and downloads a full database backup."""
    try:
        data = {
            "items": list(items_collection.find({}, {'_id': 0})),
            "categories": list(categories_collection.find({}, {'_id': 0})),
            "purchase": list(purchase_collection.find({}, {'_id': 0})),
            "sales": list(sales_collection.find({}, {'_id': 0})),
            "inventory_log": list(inventory_log_collection.find({}, {'_id': 0})),
            "system_logs": list(system_log_collection.find({}, {'_id': 0})),
            "notes": list(notes_collection.find({}, {'_id': 0})),
            "users": list(users_collection.find({}, {'_id': 0})),
            "settings": list(settings_collection.find({}, {'_id': 0}))
        }
        
        from flask import Response
        filename = f"xpider_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        return Response(
            json.dumps(data, indent=4, cls=MongoJSONEncoder),
            mimetype='application/json',
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        flash(f"Backup failed: {str(e)}", "danger")
        return redirect(url_for('admin_accounts'))

@app.route('/settings/backup/restore', methods=['POST'])
@login_required
@role_required('owner')
def restore_backup():
    """Restores database from a uploaded JSON backup file."""
    if 'backup_file' not in request.files:
        flash("No file uploaded", "danger")
        return redirect(url_for('admin_accounts'))
    
    file = request.files['backup_file']
    if file.filename == '':
        flash("No file selected", "danger")
        return redirect(url_for('admin_accounts'))

    try:
        data = json.load(file)
        
        # Mapping of keys to collections
        mapping = {
            "items": items_collection,
            "categories": categories_collection,
            "purchase": purchase_collection,
            "sales": sales_collection,
            "inventory_log": inventory_log_collection,
            "system_logs": system_log_collection,
            "notes": notes_collection,
            "users": users_collection,
            "settings": settings_collection
        }

        # Validate basic structure
        if not any(k in data for k in mapping.keys()):
            flash("Invalid backup format.", "danger")
            return redirect(url_for('admin_accounts'))

        # Perform Restoration
        for key, collection in mapping.items():
            if key in data and isinstance(data[key], list):
                # Clear existing
                collection.delete_many({})
                # Insert new if not empty
                if data[key]:
                    collection.insert_many(data[key])
        
        log_action("RESTORE_BACKUP", "Owner restored the system from a backup file.")
        flash("System restored successfully! Please log in again if user data was changed.", "success")
        
    except Exception as e:
        flash(f"Restore failed: {str(e)}", "danger")
    
    return redirect(url_for('admin_accounts'))

@app.route('/settings/backup/restore/csv', methods=['POST'])
@login_required
@role_required('owner')
def restore_csv():
    """Restores specific collections from a CSV file."""
    if 'csv_file' not in request.files:
        flash("No file uploaded", "danger")
        return redirect(url_for('admin_accounts'))
    
    file = request.files['csv_file']
    target = request.form.get('target_collection')
    
    if file.filename == '' or not target:
        flash("File or target collection missing", "danger")
        return redirect(url_for('admin_accounts'))

    try:
        import csv
        from io import StringIO
        stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        
        data_to_insert = []
        
        def clean_val(val, type_func=float):
            if not val: return 0.0 if type_func == float else 0
            # Remove currency symbols, commas, and percentage signs
            clean = val.replace("₱", "").replace(",", "").replace("%", "").strip()
            # Handle special strings like "Low Stock"
            if clean.lower() == "low stock": return 0
            try:
                return type_func(clean)
            except:
                return 0.0 if type_func == float else 0

        for row in csv_input:
            # Map user's CSV headers to database fields
            mapped_row = {}
            
            if target == 'items':
                mapped_row['name'] = row.get('Item Name', row.get('name', 'Unknown Item'))
                mapped_row['category'] = row.get('Category', row.get('category', 'Uncategorized'))
                mapped_row['cost_price'] = clean_val(row.get('Cost Price', row.get('cost_price', '0')))
                mapped_row['retail_price'] = clean_val(row.get('Retail Price', row.get('retail_price', '0')))
                mapped_row['stock'] = int(clean_val(row.get('Quantity Available', row.get('stock', '0')), int))
                mapped_row['sold'] = int(clean_val(row.get('Quantity Sale', row.get('sold', '0')), int))
                
                # Validation: Skip empty rows (where name is empty)
                if not mapped_row['name'] or mapped_row['name'].strip() == "":
                    continue
                    
                data_to_insert.append(mapped_row)
                
            elif target == 'categories':
                name = row.get('Category', row.get('name'))
                if name and name.strip() != "":
                    data_to_insert.append({"name": name.strip()})
        
        if target == 'items':
            if data_to_insert:
                # Wipe both items and categories for a clean restore
                items_collection.delete_many({})
                items_collection.insert_many(data_to_insert)
                
                # Auto-detect and rebuild categories
                unique_cats = sorted(list(set([item['category'] for item in data_to_insert if item.get('category')])))
                if unique_cats:
                    categories_collection.delete_many({})
                    categories_collection.insert_many([{"name": cat} for cat in unique_cats])
            else:
                flash("No valid data found in CSV for Items.", "warning")
                return redirect(url_for('admin_accounts'))
        elif target == 'categories':
            if data_to_insert:
                # Deduplicate categories
                unique_cats = {c['name']: c for c in data_to_insert}.values()
                categories_collection.delete_many({})
                categories_collection.insert_many(list(unique_cats))
            else:
                flash("No valid data found in CSV for Categories.", "warning")
                return redirect(url_for('admin_accounts'))
            
        log_action("RESTORE_CSV", f"Owner restored {target} collection from CSV.")
        flash(f"{target.capitalize()} restored successfully from CSV!", "success")
        
    except Exception as e:
        flash(f"CSV Restore failed: {str(e)}", "danger")
    
    return redirect(url_for('admin_accounts'))

@app.route('/settings/category/add', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('name')
    if name:
        if categories_collection.find_one({"name": name}):
            flash("Category already exists!", "danger")
        else:
            categories_collection.insert_one({"name": name})
            log_action("ADD_CATEGORY", f"Added category: {name}")
            flash(f"Category '{name}' added!", "success")
    return redirect(url_for('admin_accounts'))

@app.route('/settings/category/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_category(id):
    cat = categories_collection.find_one({"_id": ObjectId(id)})
    if cat:
        categories_collection.delete_one({"_id": ObjectId(id)})
        log_action("DELETE_CATEGORY", f"Deleted category: {cat['name']}")
        flash("Category deleted.", "info")
    return redirect(url_for('admin_accounts'))

@app.route('/settings/user/add', methods=['POST'])
@login_required
@role_required('owner')
def add_user():
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role', 'cashier')
    if email and password:
        if users_collection.find_one({"email": email}):
            flash("User already exists!", "danger")
        else:
            users_collection.insert_one({"email": email, "password": password, "role": role})
            log_action("ADD_USER", f"Created user: {email} ({role})")
            flash(f"User '{email}' created successfully!", "success")
    return redirect(url_for('admin_accounts'))

@app.route('/settings/user/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_user(id):
    user = users_collection.find_one({"_id": ObjectId(id)})
    if user:
        if user['email'] == 'admin@inventory.com':
            flash("Cannot delete the main admin account!", "danger")
        else:
            users_collection.delete_one({"_id": ObjectId(id)})
            log_action("DELETE_USER", f"Deleted user: {user['email']}")
            flash("User deleted.", "info")
    return redirect(url_for('admin_accounts'))

@app.route('/admin/send-auth-code', methods=['POST'])
@login_required
@role_required('owner')
def send_auth_code():
    code = str(random.randint(100000, 999999))
    session['auth_code'] = code
    session['auth_code_expiry'] = (datetime.now() + timedelta(minutes=10)).isoformat()
    
    # Master Email for Security Authorization
    recipient = "bejasadhev@gmail.com"
    
    subject = "Owner Security Authorization Code"
    body = f"""
    SECURITY ALERT:
    
    A request has been made to modify a protected Owner account on your XPIDER Inventory Engine.
    
    Your Authorization Code is: {code}
    
    This code will expire in 10 minutes. 
    If you did not initiate this request, please review your security logs immediately.
    """
    
    success = send_email_notification(subject, body, override_recipient=recipient)
    if success:
        return jsonify({"success": True, "message": f"Verification code sent to {recipient}"})
    else:
        return jsonify({"success": False, "message": "Failed to send email. Check SMTP settings."})

@app.route('/settings/user/edit/<id>', methods=['POST'])
@login_required
@role_required('owner')
def edit_user(id):
    user = users_collection.find_one({"_id": ObjectId(id)})
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('admin_accounts'))

    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')
    verification_code = request.form.get('verification_code')

    # Security Check: If editing a protected account or changing to owner
    is_protected = user.get('role') == 'owner' or user.get('email') == 'admin@inventory.com'
    if is_protected or role == 'owner':
        stored_code = session.get('auth_code')
        expiry_str = session.get('auth_code_expiry')
        
        if not stored_code or not expiry_str:
            flash("Authorization required. Please send a code to your email first.", "danger")
            return redirect(url_for('admin_accounts'))
            
        expiry = datetime.fromisoformat(expiry_str)
        if datetime.now() > expiry:
            flash("Security code has expired. Please request a new one.", "danger")
            return redirect(url_for('admin_accounts'))
            
        if verification_code != stored_code:
            flash("Invalid Security Code! Authorization denied.", "danger")
            return redirect(url_for('admin_accounts'))
        
        # Clear code after successful use
        session.pop('auth_code', None)
        session.pop('auth_code_expiry', None)

    update_data = {}
    if email: update_data['email'] = email
    if password: update_data['password'] = password
    if role: update_data['role'] = role

    if update_data:
        users_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        log_action("EDIT_USER", f"Updated account credentials for: {user['email']}")
        flash(f"Account for {user['email']} updated successfully!", "success")

    return redirect(url_for('admin_accounts'))

@app.route('/settings/api/update', methods=['POST'])
@login_required
@role_required('owner')
def update_api_key():
    api_key = request.form.get('api_key')
    api_type = request.form.get('api_type', 'openrouter')
    
    if api_key:
        env_path = os.path.join(os.getcwd(), '.env')
        env_var = "GEMINI_API_KEY" if api_type == 'gemini' else "OPENROUTER_API_KEY"
        
        # Logic to update .env securely
        lines = []
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = [line for line in f.readlines() if not line.startswith(f'{env_var}=')]
        
        # Clean existing lines to avoid trailing issues
        lines = [l for l in lines if l.strip()]
        
        with open(env_path, 'w') as f:
            for line in lines:
                f.write(line.strip() + '\n')
            f.write(f'{env_var}={api_key.strip()}\n')
        
        # Reload environment and engine
        import importlib
        load_dotenv(override=True)
        importlib.reload(ai_engine)
        
        log_action("UPDATE_API_KEY", f"Updated {api_type.capitalize()} API Key.")
        flash(f"{api_type.capitalize()} API Key updated successfully!", "success")
    
    return redirect(url_for('admin_accounts'))

# --- DEVELOPER PORTAL ROUTES ---

@app.route('/log-client-error', methods=['POST'])
def log_client_error():
    data = request.json
    error_msg = data.get('error', 'Unknown Error')
    url = data.get('url', 'N/A')
    line = data.get('line', 'N/A')
    col = data.get('col', 'N/A')
    stack = data.get('stack', '')
    
    user_agent = request.headers.get('User-Agent', 'Unknown')
    device = "Mobile" if "Mobi" in user_agent else "Desktop"
    
    details = f"[BROWSER-{device}] {error_msg} at {url}:{line}:{col}"
    log_action("CLIENT_ERROR", details, send_push=False)
    
    # Also log to file for the terminal stream
    print(f"ERROR: {details}")
    return jsonify({"success": True})

@app.route('/developer')
@login_required
def developer_portal():
    # Allow all roles access
    pass
    
    # Fetch Dev Updates for the portal
    dev_updates = list(dev_updates_collection.find().sort("timestamp", -1))
    
    # Check if Watchdog is active
    import subprocess
    watchdog_active = False
    try:
        # Check for the watchdog.sh process
        subprocess.check_output(["pgrep", "-f", "watchdog.sh"])
        watchdog_active = True
    except:
        watchdog_active = False

    # --- System Stats for Dev ---
    # 1. Language Stats (Line Counts)
    stats = {
        "Python": 1100, # app.py + engines
        "HTML/Jinja": 2400, # templates
        "JavaScript": 350, # logic inside templates + sw
        "CSS": 150 # styling
    }
    total_lines = sum(stats.values())
    lang_percents = {k: round((v / total_lines) * 100, 1) for k, v in stats.items()}
    
    # 2. Libraries (Key ones from pip)
    import importlib.metadata
    key_libs = ["Flask", "pymongo", "Flask-PyMongo", "pywebpush", "psutil", "requests", "python-dotenv"]
    libs = {}
    for lib in key_libs:
        try:
            libs[lib] = importlib.metadata.version(lib)
        except importlib.metadata.PackageNotFoundError:
            libs[lib] = "Installed"

    # 3. Read Tech Files for Editor
    tech_files = {}
    for filename in ['robots.txt', 'sitemap.xml', 'manifest.json']:
        path = os.path.join(os.getcwd(), 'static', filename)
        try:
            with open(path, 'r') as f:
                tech_files[filename.replace('.', '_')] = f.read()
        except:
            tech_files[filename.replace('.', '_')] = ""

    return render_template('developer.html', 
                           role=session.get('role'), 
                           dev_updates=dev_updates,
                           lang_stats=lang_percents,
                           libs=libs,
                           tech_files=tech_files,
                           watchdog_active=watchdog_active,
                           flask_debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")

@app.route('/developer/watchdog/start', methods=['POST'])
@login_required
def start_watchdog():
    # Access granted to all roles
    pass
    
    import subprocess
    import os
    try:
        # Check if already running to avoid duplicates
        subprocess.check_output(["pgrep", "-f", "watchdog.sh"])
        return jsonify({"success": True, "message": "Watchdog is already running."})
    except:
        # Start the watchdog
        base_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(base_dir, "watchdog.sh")
        # Run in background with nohup
        subprocess.Popen(["/bin/bash", script_path], 
                         stdout=open(os.devnull, 'w'), 
                         stderr=open(os.devnull, 'w'), 
                         start_new_session=True)
        log_action("WATCHDOG_START", "Developer started the system watchdog.")
        return jsonify({"success": True, "message": "Watchdog started successfully."})

@app.route('/developer/watchdog/stop', methods=['POST'])
@login_required
def stop_watchdog():
    # Access granted to all roles
    pass
    
    import subprocess
    try:
        # Kill the watchdog.sh process
        subprocess.run(["pkill", "-f", "watchdog.sh"])
        log_action("WATCHDOG_STOP", "Developer stopped the system watchdog.")
        return jsonify({"success": True, "message": "Watchdog stopped."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/developer/file/update', methods=['POST'])
@login_required
def update_tech_file():
    # Access granted to all roles
    pass
    
    filename = request.form.get('filename')
    content = request.form.get('content')
    
    if filename in ['robots.txt', 'sitemap.xml', 'manifest.json']:
        path = os.path.join(os.getcwd(), 'static', filename)
        try:
            with open(path, 'w') as f:
                f.write(content)
            log_action("UPDATE_FILE", f"Developer modified {filename}")
            return jsonify({"success": True, "message": f"{filename} updated successfully!"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})
    
    return jsonify({"success": False, "message": "Invalid filename"})

@app.route('/developer/docs')
@login_required
def developer_docs():
    # All roles allowed
    pass
    return render_template('documentation.html', role=session.get('role'))

@app.route('/developer/scan', methods=['POST'])
@login_required
def developer_scan():
    # Allowed for all roles
    pass
    
    from scanner import WebsiteScanner
    # Force scan on local loopback to bypass tailscale/proxy routing issues
    base_url = "http://127.0.0.1:5000/"
    scanner = WebsiteScanner(base_url, cookies=request.cookies)
    results = scanner.run_scan()
    
    log_action("SYSTEM_SCAN", f"Developer performed a full system health scan. Found {len(results['broken_links'])} broken links and {len(results['vulnerabilities'])} vulnerabilities.")
    
    return jsonify(results)

@app.route('/developer/live-debug')
@login_required
def live_debug():
    # All roles allowed
    pass
    return render_template('live_debug.html', role=session.get('role'))

@app.route('/developer/health-scanner')
@login_required
def health_scanner():
    # All roles allowed
    pass
    return render_template('health_scanner.html', role=session.get('role'))

@app.route('/developer/logs')
@login_required
def stream_logs():
    # All roles allowed
    pass
    try:
        with open('app_output.log', 'r') as f:
            # Return last 100 lines for the console, but filter out noise
            lines = f.readlines()
            # Filter out requests to /developer/logs to avoid visual loop
            filtered = [line for line in lines if "/developer/logs" not in line and "/system-info" not in line and "/latest-log" not in line]
            return "".join(filtered[-100:])
    except:
        return "Log file not found."

@app.route('/developer/backup')
@login_required
def developer_backup():
    # All roles allowed
    pass
    
    try:
        # Bundle all collections
        data = {
            "items": list(items_collection.find({}, {'_id': 0})),
            "categories": list(categories_collection.find({}, {'_id': 0})),
            "purchase": list(purchase_collection.find({}, {'_id': 0})),
            "inventory_log": list(inventory_log_collection.find({}, {'_id': 0})),
            "system_logs": list(system_log_collection.find({}, {'_id': 0})),
            "notes": list(notes_collection.find({}, {'_id': 0})),
            "subscriptions": list(subscriptions_collection.find({}, {'_id': 0})),
            "dev_updates": list(dev_updates_collection.find({}, {'_id': 0}))
        }
        
        from flask import Response
        return Response(
            json.dumps(data, indent=4, cls=MongoJSONEncoder),
            mimetype='application/json',
            headers={"Content-disposition": f"attachment; filename=xpider_backup_{datetime.now().strftime('%Y%m%d')}.json"}
        )
    except Exception as e:
        print(f"[BACKUP-ERROR] {e}")
        flash(f"Backup failed: {e}", "danger")
        return redirect(url_for('developer_portal'))

@app.route('/developer/server/restart', methods=['POST'])
@login_required
def server_restart():
    # ... existing implementation ...
    # Access granted to all roles
    pass
    
    log_action("SERVER_RESTART", "Developer triggered remote server restart.")
    
    import subprocess
    import sys
    import time
    
    def perform_restart():
        time.sleep(1) # Wait for response to be sent
        
        script_path = os.path.abspath(__file__)
        py_path = sys.executable
        cwd = os.path.dirname(script_path)
        log_path = os.path.join(cwd, 'app_output.log')

        # Kill whatever is on port 5000 and start fresh
        # fuser -k 5000/tcp is the most reliable way to free the port
        cmd = f"sleep 2 && fuser -k 5000/tcp ; nohup {py_path} {script_path} >> {log_path} 2>&1 &"        
        subprocess.Popen(['/bin/bash', '-c', cmd], cwd=cwd, start_new_session=True)
        os._exit(0)
    
    # Run restart in a separate thread/greenlet to not block the response
    import eventlet
    eventlet.spawn_after(0.5, perform_restart)
    
    return jsonify({"success": True, "message": "Server rebooting... reconnecting in 5s."})

@app.route('/developer/server/toggle-debug', methods=['POST'])
@login_required
def toggle_debug():
    # Access granted to all roles
    pass
    
    # Precise .env path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base_dir, '.env')
    
    current_debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    new_debug = not current_debug
    
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.strip().startswith("FLASK_DEBUG="):
                    lines.append(f"FLASK_DEBUG={'true' if new_debug else 'false'}\n")
                    found = True
                else:
                    lines.append(line)
    
    if not found:
        lines.append(f"FLASK_DEBUG={'true' if new_debug else 'false'}\n")
        
    with open(env_path, 'w') as f:
        f.writelines(lines)
    
    # Update environment variable for current process (though it will restart)
    os.environ["FLASK_DEBUG"] = 'true' if new_debug else 'false'
    
    log_action("DEBUG_TOGGLE", f"Debug Mode set to {new_debug}")
    return server_restart()

# --- Real-time Socket Diagnostics ---
online_users = {} # sid -> user_info

@app.route('/debugging-ai')
@login_required
def debugging_ai():
    # All roles allowed
    pass
    return render_template('debugging_ai.html', role=session.get('role'))

@app.route('/debugging-ai/scan', methods=['POST'])
@login_required
def scan_website():
    # Allowed for all roles
    pass

    # Use 127.0.0.1:5000 for internal crawling to avoid proxy/DNS issues
    # but use the request cookies to stay authenticated.
    base_url = "http://127.0.0.1:5000"
    
    # Run the scan
    scan_results = ai_engine.run_full_site_scan(base_url, cookies=request.cookies)
    
    return jsonify({
        "success": True, 
        "data": scan_results
    })

@app.route('/debugging-ai/fix', methods=['POST'])
@login_required
def fix_error():
    # Allowed for all roles
    pass
        
    try:
        error_context = request.json.get('context', 'Unknown Error')
        print(f"[AI-FIX] Analyzing error: {error_context}")
        
        prompt = f"""
        A website error was detected. 
        ERROR CONTEXT: {error_context}
        
        Please provide a specific code fix or explanation for this error. 
        If it's a 404, suggest checking routes.
        If it's a 500, suggest checking server logs or specific code sections if context is given.
        If it's a client-side error, suggest a JS fix.
        
        System: XPIDER Inventory (Flask/MongoDB)
        """
        
        fix_suggestion = ai_engine.get_ai_response(prompt)
        return jsonify({"success": True, "fix": fix_suggestion})
    except Exception as e:
        print(f"[AI-FIX] System Error: {e}")
        return jsonify({"success": False, "message": str(e)})

@app.route('/debugging-ai/analyze', methods=['POST'])
@login_required
def ai_analyze_errors():
    # Access granted to all roles
    pass
    
    # 1. Gather Context: Latest System Logs & Browser Errors
    sys_logs = list(system_log_collection.find().sort("timestamp", -1).limit(15))
    
    log_summary = ""
    for l in sys_logs:
        log_summary += f"[{l.get('timestamp')}] {l.get('action')}: {l.get('details')}\n"

    # 2. Build the Technical Prompt
    prompt = f"""
    You are the XPIDER System Architect. Analyze the following system logs and telemetry:
    
    SYSTEM LOGS:
    {log_summary}
    
    TASK:
    1. Identify any recurring patterns of failure.
    2. Check for unauthorized access attempts.
    3. If there are [BROWSER] errors, explain the root cause in the code.
    4. Provide a 3-step action plan to improve system stability.
    
    Format your response in clean Markdown with technical sections.
    """
    
    try:
        analysis = ai_engine.get_ai_response(prompt)
        return jsonify({"success": True, "analysis": analysis})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

def emit_online_users():
    # Group by email to count unique users/sessions
    unique_users = []
    seen_emails = set()
    for sid, info in online_users.items():
        if info['email'] not in seen_emails:
            unique_users.append(info)
            seen_emails.add(info['email'])
    
    print(f"[DEBUG] Emitting Online Users: {len(unique_users)} users", flush=True)
    socketio.emit('online_users_update', {
        'count': len(unique_users),
        'users': unique_users
    })

@socketio.on('connect')
def handle_connect():
    email = session.get('email', 'Guest')
    role = session.get('role', 'N/A')
    
    online_users[request.sid] = {
        'email': email,
        'role': role,
        'since': datetime.now().strftime('%I:%M %p')
    }
    print(f"[DEBUG] Connected: {email} ({request.sid})", flush=True)
    emit_online_users()
    
    # Send a "Welcome Back" message
    emit('system_update', {
        'action': 'SERVER_READY',
        'email': 'System',
        'details': 'XPIDER Engine is fully operational and synchronized.',
        'timestamp': datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
    })

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in online_users:
        del online_users[request.sid]

    emit_online_users()

@app.route('/bulletin')
@login_required
def bulletin():
    # Auto-deletion of 'done' notes older than 1 week
    one_week_ago = datetime.now() - timedelta(days=7)

    notes_collection.delete_many({
        "status": "done",
        "done_at": {"$lt": one_week_ago}
    })

    # Sort by status (pending first), then pinned (descending), then by timestamp
    all_notes = list(notes_collection.find().sort([
        ("status", -1), 
        ("pinned", -1), 
        ("timestamp", -1)
    ]))
    return render_template('notes.html', notes=all_notes, role=session.get('role'))

@app.route('/bulletin/add', methods=['POST'])
@login_required
def add_bulletin():
    content = request.form.get('content')
    color = request.form.get('color', 'blue')
    tag = request.form.get('tag', 'Normal') # Urgent, Normal, Pending
    if content:
        note_id = notes_collection.insert_one({
            "content": content,
            "color": color,
            "tag": tag,
            "author": session.get('email'),
            "timestamp": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'),
            "pinned": False,
            "status": "pending",
            "done_at": None,
            "done_by": None
        }).inserted_id
        log_action("ADD_BULLETIN", f"Created a {tag} bulletin.")
    return redirect(url_for('bulletin'))

@app.route('/bulletin/edit/<id>', methods=['POST'])
@login_required
def edit_bulletin(id):
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if not note or note.get('author') != session.get('email'):
        flash("Unauthorized: Only the author can edit this post.", "danger")
        return redirect(url_for('bulletin'))

    content = request.form.get('content')
    tag = request.form.get('tag')
    color = request.form.get('color')

    update_data = {}
    if content: update_data['content'] = content
    if tag: update_data['tag'] = tag
    if color: update_data['color'] = color

    if update_data:
        notes_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
        log_action("EDIT_BULLETIN", "Updated a bulletin post.")
        flash("Bulletin updated!", "success")

    return redirect(url_for('bulletin'))

@app.route('/bulletin/toggle_status/<id>', methods=['POST'])
@login_required
def toggle_bulletin_status(id):
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if note:
        current_status = note.get('status', 'pending')
        new_status = 'done' if current_status == 'pending' else 'pending'
        done_at = datetime.now() if new_status == 'done' else None
        done_by = session.get('email') if new_status == 'done' else None

        notes_collection.update_one(
            {"_id": ObjectId(id)}, 
            {"$set": {"status": new_status, "done_at": done_at, "done_by": done_by}}
        )
        log_action("UPDATE_BULLETIN_STATUS", f"Bulletin marked as {new_status} by {session.get('email')}.")
    return redirect(url_for('bulletin'))

@app.route('/bulletin/update_color/<id>', methods=['POST'])
@login_required
def update_bulletin_color(id):
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if not note or note.get('author') != session.get('email'):
        return redirect(url_for('bulletin'))

    color = request.form.get('color')
    if color:
        notes_collection.update_one(
            {"_id": ObjectId(id)}, 
            {"$set": {"color": color}}
        )
    return redirect(url_for('bulletin'))

@app.route('/bulletin/pin/<id>', methods=['POST'])
@login_required
def pin_bulletin(id):
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if note:
        new_status = not note.get('pinned', False)
        notes_collection.update_one({"_id": ObjectId(id)}, {"$set": {"pinned": new_status}})
    return redirect(url_for('bulletin'))

@app.route('/bulletin/delete/<id>', methods=['POST'])
@login_required
def delete_bulletin(id):
    note = notes_collection.find_one({"_id": ObjectId(id)})
    if note and note.get('author') == session.get('email'):
        notes_collection.delete_one({"_id": ObjectId(id)})
        log_action("DELETE_BULLETIN", "Author removed a bulletin.")
        flash("Bulletin removed.", "info")
    else:
        flash("Unauthorized deletion attempt.", "danger")
    return redirect(url_for('bulletin'))
@app.route('/settings/smtp/update', methods=['POST'])
@login_required
@role_required('owner')
def update_smtp():
    host = request.form.get('smtp_host')
    port = request.form.get('smtp_port')
    user = request.form.get('smtp_user')
    passw = request.form.get('smtp_pass')
    
    env_path = os.path.join(os.getcwd(), '.env')
    keys = {
        'SMTP_HOST': host,
        'SMTP_PORT': port,
        'SMTP_USER': user,
        'SMTP_PASS': passw
    }
    
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
            
    # Filter out existing SMTP keys
    lines = [line for line in lines if not any(line.startswith(k + '=') for k in keys.keys())]
    
    with open(env_path, 'w') as f:
        for line in lines:
            f.write(line)
        for k, v in keys.items():
            f.write(f'{k}={v}\n')
            
    load_dotenv(override=True)
    log_action("UPDATE_SMTP", "Updated SMTP Configuration.")
    flash("SMTP settings saved successfully!", "success")
    return redirect(url_for('admin_accounts'))

@app.route('/settings/smtp/test', methods=['POST'])
@login_required
@role_required('owner')
def test_smtp():
    host = request.form.get('smtp_host')
    port_str = request.form.get('smtp_port', '587')
    port = int(port_str) if port_str.isdigit() else 587
    user = request.form.get('smtp_user')
    passw = request.form.get('smtp_password')
    sender = request.form.get('smtp_sender') or user
    use_tls = request.form.get('smtp_use_tls') == 'on'
    use_ssl = request.form.get('smtp_use_ssl') == 'on'
    test_email = request.form.get('test_email')

    if not all([host, user, passw, test_email]):
        return jsonify({"success": False, "message": "All fields are required for the test."})

    try:
        msg = MIMEText("This is a test email from your XPIDER Inventory System. If you are reading this, your SMTP configuration is working correctly!")
        msg['Subject'] = "XPIDER SMTP Test Connection"
        msg['From'] = sender
        msg['To'] = test_email

        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
            server.ehlo()
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.ehlo()
            # Auto-enable TLS for port 587 or if explicitly requested
            if use_tls or port == 587:
                server.starttls()
                server.ehlo()
        
        server.login(user, passw)
        server.send_message(msg)
        server.quit()
        
        return jsonify({"success": True, "message": "Test email sent successfully! Please check your inbox."})
    except Exception as e:
        return jsonify({"success": False, "message": f"SMTP Test Failed: {str(e)}"})

@app.route('/settings/data/clear', methods=['POST'])
@login_required
@role_required('owner')
def clear_all_data():
    verification_code = request.form.get('verification_code')
    stored_code = session.get('auth_code')
    expiry_str = session.get('auth_code_expiry')
    
    if not stored_code or not expiry_str:
        flash("Authorization required. Please send a code to your email first.", "danger")
        return redirect(url_for('general_setup'))
        
    expiry = datetime.fromisoformat(expiry_str)
    if datetime.now() > expiry:
        flash("Security code has expired. Please request a new one.", "danger")
        return redirect(url_for('general_setup'))
        
    if verification_code != stored_code:
        flash("Invalid Security Code! Data wipe denied.", "danger")
        return redirect(url_for('general_setup'))

    # Clear code after use
    session.pop('auth_code', None)
    session.pop('auth_code_expiry', None)

    # Collections to wipe
    collections = [items_collection, purchase_collection, inventory_log_collection, system_log_collection]
    for col in collections:
        col.delete_many({})
    
    log_action("CLEAR_DATABASE", "Owner wiped all business records.")
    flash("All business data has been cleared successfully!", "warning")
    return redirect(url_for('general_setup'))

@app.route('/import/csv', methods=['POST'])
@login_required
def import_csv():
    if 'csv_file' not in request.files:
        flash("No file uploaded", "danger")
        return redirect(url_for('items'))
    
    file = request.files['csv_file']
    if file.filename == '':
        flash("No selected file", "danger")
        return redirect(url_for('items'))

    try:
        import csv
        from io import StringIO
        stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        
        count = 0
        for row in csv_input:
            # Match CSV headers to DB fields
            item_data = {
                "name": row.get('Item Name'),
                "category": row.get('Category', 'Uncategorized'),
                "cost_price": float(row.get('Cost Price', 0).replace('₱', '').replace(',', '')),
                "retail_price": float(row.get('Retail Price', 0).replace('₱', '').replace(',', '')),
                "stock": int(row.get('Stock', 0)),
                "sold": int(row.get('Sold', 0))
            }
            
            if item_data['name']:
                # Update if exists, otherwise insert
                items_collection.update_one(
                    {"name": item_data['name']},
                    {"$set": item_data},
                    upsert=True
                )
                count += 1
        
        log_action("IMPORT_CSV", f"Imported {count} items from CSV.")
        flash(f"Successfully imported {count} items!", "success")
    except Exception as e:
        flash(f"Import failed: {str(e)}", "danger")
        
    return redirect(url_for('items'))

@app.route('/export/csv')
@login_required
def export_csv():
    try:
        import csv; from io import StringIO; from flask import make_response
        si = StringIO(); cw = csv.writer(si)
        cw.writerow(['Item Name', 'Category', 'Cost Price', 'Retail Price', 'Stock', 'Sold', 'Inventory Value', 'Total Revenue'])
        for item in items_collection.find():
            m = calculate_item_metrics(item)
            cw.writerow([m['name'], m['category'], m['cost_price'], m['retail_price'], m['stock'], m['sold'], m['inventory_value'], m['total_revenue']])
        
        log_action("EXPORT_CSV", "Exported inventory master list to CSV.")
        
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = "attachment; filename=inventory_export.csv"
        output.headers["Content-type"] = "text/csv"
        return output
    except Exception as e:
        print(f"[EXPORT-ERROR] {e}")
        flash(f"Export failed: {e}", "danger")
        return redirect(url_for('items'))

@app.route('/logout')
def logout():
    user_email = session.get('email', 'Unknown')
    log_action("LOGOUT", f"User '{user_email}' logged out.")
    session.clear()
    return redirect(url_for('index'))

@app.route('/system-info')
@login_required
def system_info():
    try:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return jsonify({
            'cpu': cpu,
            'ram_percent': ram.percent,
            'ram_used': f"{ram.used / (1024**3):.1f}GB",
            'ram_total': f"{ram.total / (1024**3):.1f}GB",
            'disk_percent': disk.percent,
            'disk_free': f"{disk.free / (1024**3):.1f}GB"
        })
    except Exception as e:
        print(f"[SYSTEM-INFO-ERROR] {e}")
        return jsonify({
            'cpu': 0,
            'ram_percent': 0,
            'ram_used': '0GB',
            'ram_total': '0GB',
            'disk_percent': 0,
            'disk_free': '0GB'
        })

@app.route('/latest-log')
@login_required
def latest_log():
    # Fetch only the single most recent log
    log = system_log_collection.find_one(sort=[("timestamp", -1)])
    if log:
        return jsonify({
            "action": log.get('action'),
            "email": log.get('email', log.get('username', 'System')),
            "timestamp": log.get('timestamp')
        })
    return jsonify({})

@app.route('/sw.js')
def serve_sw():
    from flask import send_from_directory
    # Prefer serving from root if it exists there, otherwise from static
    if os.path.exists(os.path.join(app.root_path, 'sw.js')):
        return send_from_directory(app.root_path, 'sw.js', mimetype='application/javascript')
    return send_from_directory(os.path.join(app.root_path, 'static'), 'sw.js', mimetype='application/javascript')

@app.route('/manifest.json')
def serve_manifest():
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.root_path, 'static'), 'manifest.json')

@app.route('/robots.txt')
def serve_robots():
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.root_path, 'static'), 'robots.txt')

@app.route('/sitemap.xml')
def serve_sitemap():
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.root_path, 'static'), 'sitemap.xml')

if __name__ == '__main__':
    HOST = '0.0.0.0'
    PORT = 5000
    DEBUG_MODE = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"Starting REAL-TIME server on {HOST}:{PORT} (Debug: {DEBUG_MODE})")
    
    # Diagnostic: Print all routes
    print("--- REGISTERED ROUTES ---")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.rule}")
    print("-------------------------")
    
    socketio.run(app, host=HOST, port=PORT, debug=DEBUG_MODE, use_reloader=DEBUG_MODE)
