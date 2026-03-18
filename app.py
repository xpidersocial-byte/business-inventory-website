import eventlet
eventlet.monkey_patch()

import os
from flask import Flask, render_template, request, session, g, jsonify
from datetime import datetime
from dotenv import load_dotenv

from extensions import mongo, socketio
from core.utils import get_site_config, MongoJSONProvider
from core.middleware import get_cashier_permissions, login_required
from core.db import get_users_collection
from core.sockets import init_socket_handlers

# Import Blueprints
from routes.auth import auth_bp
from routes.dashboard import dashboard_bp
from routes.inventory import inventory_bp
from routes.sales import sales_bp
from routes.admin import admin_bp
from routes.developer import developer_bp
from routes.ai import ai_bp
from routes.notes import bulletin_bp

load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")
app.json = MongoJSONProvider(app)

# MongoDB Configuration
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/flask_todo_db")
mongo.init_app(app)

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
app.register_blueprint(ai_bp)
app.register_blueprint(bulletin_bp)

# SECTION: Global Handlers & Filters

@app.before_request
def maintenance_mode_check():
    config = get_site_config()
    if config.get('maintenance_mode', False):
        exempt_routes = ['auth.login', 'auth.index', 'static']
        if request.endpoint and request.endpoint not in exempt_routes:
            return render_template('maintenance.html', config=config), 503

@app.before_request
def load_user_theme():
    if 'email' in session:
        users_collection = get_users_collection()
        user = users_collection.find_one({"email": session['email']}, {"theme": 1})
        if user:
            g.theme = user.get('theme', 'default')
            session['theme'] = g.theme

@app.after_request
def add_security_headers(response):
    # Expanded CSP to allow Google Fonts, Three.js, and clarify WebSocket origins
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdn.socket.io https://cdnjs.cloudflare.com https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://fonts.bunny.net; "
        "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com; "
        "img-src 'self' data: https://placehold.co https://*.googleusercontent.com https://*.google.com; "
        "frame-src 'self' https://drive.google.com https://*.google.com; "
        "connect-src 'self' https://cdn.jsdelivr.net https://cdn.socket.io https://fonts.googleapis.com https://fonts.gstatic.com ws: wss: http://127.0.0.1:5000 ws://127.0.0.1:5000 http://localhost:5000 ws://localhost:5000;"
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
    return dict(
        site_config=get_site_config(),
        cashier_perms=get_cashier_permissions()
    )


@app.route('/system-info')
@login_required
def system_info():
    import psutil
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
        return jsonify({'cpu': 0, 'ram_percent': 0, 'ram_used': '0GB', 'ram_total': '0GB', 'disk_percent': 0, 'disk_free': '0GB'})

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
    socketio.run(app, host="0.0.0.0", port=5000, debug=os.getenv("FLASK_DEBUG", "false").lower() == "true", use_reloader=False)
