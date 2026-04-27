import eventlet
eventlet.monkey_patch(all=True)

import os
import socket
import platform
import requests
from flask import Flask, render_template, request, session, g, jsonify, redirect, url_for
from flask_compress import Compress
from datetime import datetime, timezone
from dotenv import load_dotenv

from extensions import mongo, socketio
from apscheduler.schedulers.background import BackgroundScheduler
from core.utils import get_site_config, MongoJSONProvider, send_deployment_telemetry, generate_sales_summary, reschedule_periodic_jobs
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
from routes.system import system_bp
from routes.docs import docs_bp
from routes.branches import branches_bp


load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")
app.json = MongoJSONProvider(app)

# Register Custom Jinja Filters
@app.template_filter('format_datetime')
def format_datetime(value, format="%Y-%m-%d %I:%M %p"):
    if not value:
        return ""
    if isinstance(value, str):
        try:
            # Handle various formats found in logs, prioritizing ISO for performance
            for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %I:%M:%S %p', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %I:%M %p']:
                try:
                    return datetime.strptime(value, fmt).strftime(format)
                except ValueError:
                    continue
            return value # Fallback if no format matches
        except:
            return value
    try:
        return value.strftime(format)
    except:
        return value

# MongoDB Configuration
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/database?directConnection=true&serverSelectionTimeoutMS=2000&appName=mongosh+2.8.1")
mongo.init_app(app)

# Enable Compression
Compress(app)

# SocketIO Initialization
socketio.init_app(app, cors_allowed_origins="*", async_mode='eventlet')
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
app.register_blueprint(docs_bp)
app.register_blueprint(system_bp)
app.register_blueprint(branches_bp)

# Background Tasks setup
app.scheduler = BackgroundScheduler(daemon=True)
scheduler = app.scheduler
scheduler.start()
reschedule_periodic_jobs(scheduler)



# Legacy URL redirect: /inventory -> /items
@app.route('/inventory')
def inventory_redirect():
    return redirect(url_for("inventory.items"), 301)

# SECTION: Global Handlers & Filters

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')

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
           request.path.startswith('/api') or \
           'application/json' in request.headers.get('Accept', ''):
            return jsonify({"error": "Database unavailable", "offline": True}), 503
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
        # Update last active timestamp using UTC
        try:
            users_collection.update_one(
                {"email": session['email']},
                {"$set": {"last_active": datetime.now(timezone.utc)}}
            )
        except: pass

@app.context_processor
def inject_globals():
    config = get_site_config()
    branch_name = "Global View"
    available_branches = []
    
    if session.get('branch_id'):
        from core.db import get_branches_collection
        from bson.objectid import ObjectId
        try:
            b = get_branches_collection().find_one({"_id": ObjectId(session['branch_id'])})
            if b: branch_name = b.get('name', 'Unknown Branch')
        except: pass

    if 'email' in session:
        from core.db import get_branches_collection
        available_branches = list(get_branches_collection().find({"active": True}).sort("name", 1))

    return {
        'site_config': config,
        'current_user': get_users_collection().find_one({"email": session.get('email')}) if 'email' in session else None,
        'cashier_perms': get_cashier_permissions() if 'email' in session else {},
        'owner_perms': get_owner_permissions(),
        'available_branches': available_branches,
        'current_branch_name': branch_name,
        'vapid_public_key': os.getenv('VAPID_PUBLIC_KEY', '')
    }

@app.route('/health')
def health_check():
    try:
        get_items_collection().find_one()
        return jsonify({"status": "healthy", "db": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "db": "disconnected", "error": str(e)}), 503

@app.after_request
def add_security_headers(response):
    # Fixed NameError by using string literals
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
    response.headers['X-Xss-Protection'] = '1; mode=block'
    return response

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    send_deployment_telemetry()
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    host = os.getenv("HOST", "0.0.0.0")
    if host == "0.0.0.0":
        # Prefer IPv6 dual-stack on local dev so localhost resolves properly.
        try:
            socket.getaddrinfo("::1", port, socket.AF_INET6, socket.SOCK_STREAM)
            host = "::"
        except Exception:
            host = "0.0.0.0"

    socketio.run(app, host=host, port=port, debug=debug_mode, use_reloader=False)
