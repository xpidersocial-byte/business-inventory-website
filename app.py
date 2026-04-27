import eventlet
eventlet.monkey_patch()

import os
from flask import Flask, render_template, request, session, g, jsonify, redirect, url_for
from flask_pymongo import PyMongo
from flask_socketio import SocketIO
from flask_compress import Compress
from datetime import datetime, timezone
from dotenv import load_dotenv
from bson.objectid import ObjectId

# Import Extensions & Core
from extensions import mongo, socketio, scheduler
from core.utils import MongoJSONProvider, reschedule_periodic_jobs, get_site_config
from core.db import get_users_collection, get_branches_collection
from core.middleware import get_cashier_permissions, get_owner_permissions
from core.sockets import init_socket_handlers

def create_app():
    # Load environment variables
    load_dotenv()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "xpider-inventory-nexus-2026-secure")
    app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/inventory_db")
    app.json = MongoJSONProvider(app)

    # Initialize Extensions
    mongo.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='eventlet')
    Compress(app)
    
    # Initialize Socket Handlers
    init_socket_handlers()

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

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.inventory import inventory_bp
    from routes.sales import sales_bp
    from routes.branches import branches_bp
    from routes.system import system_bp
    from routes.admin import admin_bp
    from routes.developer import developer_bp
    from routes.notes import bulletin_bp
    from routes.docs import docs_bp
    from routes.pos import pos_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(branches_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(developer_bp)
    app.register_blueprint(bulletin_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(pos_bp)

    # SECTION: Global Handlers & Filters

    @app.route('/favicon.ico')
    def favicon():
        return app.send_static_file('favicon.ico')

    @app.route('/inventory')
    def inventory_redirect():
        """Legacy URL redirect: /inventory -> /items"""
        return redirect(url_for("inventory.items"), 301)

    @app.route('/health')
    def health_check():
        """Health check endpoint for monitoring."""
        try:
            from core.db import get_items_collection
            get_items_collection().find_one()
            return jsonify({"status": "healthy", "db": "connected"}), 200
        except Exception as e:
            return jsonify({"status": "unhealthy", "db": "disconnected", "error": str(e)}), 503

    @app.before_request
    def maintenance_mode_check():
        # Allow static files and login always
        if request.path.startswith('/static'):
            return
            
        config = get_site_config()
        if config.get('maintenance_mode', False):
            # Exempt routes
            exempt_endpoints = ['auth.login', 'auth.index', 'auth.logout', 'admin.update_settings', 'admin.update_general_settings']
            
            # CRITICAL: Allow Owner to access settings even in maintenance mode so they can turn it off!
            if session.get('role') == 'owner':
                return

            if request.endpoint and request.endpoint not in exempt_endpoints:
                # If it's an API request, return JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api'):
                    return jsonify({"error": "System is under maintenance", "maintenance": True}), 503
                return render_template('maintenance.html', config=config), 503

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

    @app.after_request
    def add_security_headers(response):
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

    @app.context_processor
    def inject_global_data():
        config = get_site_config()
        branch_name = "Danao"
        available_branches = []
        
        if session.get('branch_id'):
            try:
                b = get_branches_collection().find_one({"_id": ObjectId(session['branch_id'])})
                if b: branch_name = b.get('name', 'Unknown Branch')
            except: pass

        if 'email' in session and session.get('role') == 'owner':
            available_branches = list(get_branches_collection().find({"active": True}).sort("name", 1))

        return {
            'site_config': config,
            'current_user': get_users_collection().find_one({"email": session.get('email')}) if 'email' in session else None,
            'cashier_perms': get_cashier_permissions() if 'email' in session else {},
            'owner_perms': get_owner_permissions(),
            'available_branches': available_branches,
            'current_branch_name': branch_name,
            'vapid_public_key': os.getenv('VAPID_PUBLIC_KEY', ''),
            'now': datetime.now(timezone.utc)
        }

    # Start Scheduler
    if not scheduler.running:
        scheduler.start()
        with app.app_context():
            reschedule_periodic_jobs(scheduler)

    return app

app = create_app()

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
