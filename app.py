import os
from flask import Flask, render_template, request, session, g, jsonify, redirect, url_for
from flask_pymongo import PyMongo
from flask_socketio import SocketIO
from flask_compress import Compress
from datetime import datetime, timezone
from dotenv import load_dotenv

# Import Extensions & Core
from extensions import mongo, socketio, scheduler
from core.utils import MongoJSONProvider, reschedule_periodic_jobs, get_site_config

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

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.inventory import inventory_bp
    from routes.sales import sales_bp
    from routes.branches import branches_bp
    from routes.system import system_bp
    from routes.admin import admin_bp
    from routes.developer import dev_bp
    from routes.notes import notes_bp
    from routes.docs import docs_bp
    from routes.pos import pos_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(branches_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(dev_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(pos_bp)

    # SECTION: Global Handlers & Filters

    @app.route('/favicon.ico')
    def favicon():
        return app.send_static_file('favicon.ico')

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
        return {
            "site_config": get_site_config(),
            "now": datetime.now(timezone.utc)
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
