from gevent import monkey
monkey.patch_all()

import os
import socket
import platform
import requests
from flask import Flask, render_template, request, session, g, jsonify, redirect, url_for
from datetime import datetime
from dotenv import load_dotenv

from extensions import mongo, socketio
from core.utils import get_site_config, MongoJSONProvider, send_deployment_telemetry
from core.middleware import get_cashier_permissions, get_owner_permissions, login_required
from core.db import get_users_collection, get_notes_collection, get_items_collection
from core.sockets import init_socket_handlers

# Import Blueprints
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.inventory import inventory_bp
from routes.sales import sales_bp
from routes.admin import admin_bp
from routes.developer import developer_bp
from routes.notes import bulletin_bp
from routes.pos import pos_bp

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")
app.json = MongoJSONProvider(app)

# MongoDB Configuration
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/inventory_db?directConnection=true&serverSelectionTimeoutMS=2000&appName=mongosh+2.8.1")
mongo.init_app(app)

# SocketIO Initialization
socketio.init_app(app, cors_allowed_origins="*", async_mode='gevent')
init_socket_handlers()

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(inventory_bp)
app.register_blueprint(sales_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(developer_bp)
app.register_blueprint(bulletin_bp)
app.register_blueprint(pos_bp)


# Legacy URL redirect: /inventory -> /items
@app.route('/inventory')
def inventory_redirect():
    return redirect(url_for("inventory.items"), 301)

# SECTION: Global Handlers & Filters

@app.before_request
def maintenance_mode_check():
    config = get_site_config()
    if config.get('maintenance_mode', False):
        exempt_routes = ['auth.login', 'auth.index', 'static']
        if request.endpoint and request.endpoint not in exempt_routes:
            return render_template('maintenance.html', config=config), 503

@app.errorhandler(Exception)
def handle_db_error(e):
    """Global handler: if MongoDB drops, redirect to /offline instead of 500."""
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e

    from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure, AutoReconnect
    if isinstance(e, (ServerSelectionTimeoutError, ConnectionFailure, AutoReconnect)):
        if request.path == '/health':
            return jsonify({"status": "degraded", "db": "disconnected"}), 503
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
           request.path.startsWith('/api') or \
           'application/json' in request.headers.get('Accept', ''):
            return jsonify({"error": "Database unavailable", "offline": true}), 503
        return render_template('offline.html'), 503
    raise e

@app.before_request
def load_user_theme():
    config = get_site_config()
    default_theme = config.get('default_theme', 'facebook')
    
    # Default to site-wide default theme
    g.theme = default_theme
    if 'email' in session:
        users_collection = get_users_collection()
        # Update last active timestamp
        users_collection.update_one(
            {"email": session['email']},
            {"$set": {"last_active": datetime.now()}}
        )
        
        user = users_collection.find_one({"email": session['email']}, {"theme": 1})
        if user:
            g.theme = user.get('theme', default_theme)
            session['theme'] = g.theme
        else:
            # Safety: session exists but user is gone from DB
            session.clear()
            g.theme = default_theme
    else:
        # Check if theme is in session for non-logged in users
        g.theme = session.get('theme', default_theme)

@app.after_request
def add_security_headers(response):
    # Expanded CSP
    p = "5000"
    csp = (
        "default-src 'self' https:; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdn.socket.io https://cdnjs.cloudflare.com https://unpkg.com https://static.cloudflareinsights.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://fonts.bunny.net; "
        "img-src 'self' data: https: blob:; "
        "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
        "connect-src 'self' https://raw.githubusercontent.com https://cdn.jsdelivr.net https://cdn.socket.io https://fonts.googleapis.com https://fonts.gstatic.com https://www.fbihm.online wss://www.fbihm.online https://static.cloudflareinsights.com https://cloudflareinsights.com ws: wss: http://127.0.0.1:5000 ws://127.0.0.1:5000 http://localhost:5000 ws://localhost:5000; "
        "frame-src 'self' https://challenges.cloudflare.com; "
        "media-src 'self' https: blob:; "
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.template_filter('format_datetime')
def format_datetime(value):
    if not value:
        return ""
    try:
        dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%Y-%m-%d %I:%M:%S %p')
    except ValueError:
        try:
            dt = datetime.strptime(value, '%Y-%m-%d %I:%M:%S %p')
            return dt.strftime('%Y-%m-%d %I:%M:%S %p')
        except ValueError:
            return value

@app.context_processor
def inject_globals():
    user = None
    user_email = session.get('email')
    if user_email:
        user = get_users_collection().find_one({"email": user_email})
    
    site_config = get_site_config()
    
    # Persistent Unread Bulletins (Notes)
    # Check if user is in 'read_by' array
    unread_bulletins = 0
    if user_email:
        unread_bulletins = get_notes_collection().count_documents({
            "status": {"$ne": "deleted"},
            "read_by": {"$ne": user_email}
        })
    else:
        unread_bulletins = get_notes_collection().count_documents({"status": "pending"})

    # Low Stock Count (Items)
    # Filter by threshold from config and EXCLUDE items that user has already "read"
    low_stock_threshold = site_config.get('low_stock_threshold', 5)
    
    # Base query for low stock
    query = {
        "active": {"$ne": False},
        "stock": {"$lte": low_stock_threshold}
    }
    
    # If user has read some, exclude them from the badge count
    if user and user.get('read_notif_ids'):
        from bson import ObjectId
        read_ids = []
        for rid in user['read_notif_ids']:
            try: read_ids.append(ObjectId(rid))
            except: pass
        if read_ids:
            query["_id"] = {"$nin": read_ids}
            
    low_stock_count = get_items_collection().count_documents(query)

    return dict(
        site_config=site_config,
        cashier_perms=get_cashier_permissions(),
        owner_perms=get_owner_permissions(),
        current_user=user,
        unread_bulletins=unread_bulletins,
        low_stock_count=low_stock_count
    )


@app.route('/system-info')
@login_required
def system_info():
    import psutil
    try:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Get static info
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        try:
            public_ip = requests.get('https://api.ipify.org', timeout=2).text
        except:
            public_ip = "Offline/Hidden"

        return jsonify({
            'cpu': cpu,
            'ram_percent': ram.percent,
            'ram_used': f"{ram.used / (1024**3):.1f}GB",
            'ram_total': f"{ram.total / (1024**3):.1f}GB",
            'disk_percent': disk.percent,
            'disk_free': f"{disk.free / (1024**3):.1f}GB",
            'hostname': hostname,
            'local_ip': local_ip,
            'public_ip': public_ip,
            'os': f"{platform.system()} {platform.release()}",
            'python_v': platform.python_version()
        })
    except Exception as e:
        print(f"[SYSTEM-INFO-ERROR] {e}")
        return jsonify({'cpu': 0, 'ram_percent': 0, 'ram_used': '0GB', 'ram_total': '0GB', 'disk_percent': 0, 'disk_free': '0GB'})

@app.route('/offline')
def offline():
    return render_template('offline.html')

@app.route('/health')
def health_check():
    """DB health check — used by the frontend to detect disconnections."""
    from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
    try:
        mongo.db.command('ping')
        return jsonify({"status": "ok", "db": "connected"})
    except (ServerSelectionTimeoutError, ConnectionFailure, Exception):
        return jsonify({"status": "degraded", "db": "disconnected"}), 503

@app.route('/latest-log')
@login_required
def latest_log():
    from core.db import get_system_log_collection
    system_log_collection = get_system_log_collection()
    log = system_log_collection.find_one(sort=[("timestamp", -1)])
    if log:
        return jsonify({
            "action": log.get('action'),
            "email": log.get('email', 'System'),
            "timestamp": log.get('timestamp')
        })
    return jsonify({})

@app.route('/sw.js')
def serve_sw():
    from flask import send_from_directory
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


@app.route('/favicon.ico')
def favicon():
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"DEBUG: STARTING ON PORT {port}")
    send_deployment_telemetry()
    # Enabled reloader to pick up blueprint changes
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    socketio.run(app, host="0.0.0.0", port=port, debug=debug_mode, use_reloader=debug_mode)
