from flask import Blueprint, render_template, request, jsonify, session, current_app, Response, flash, redirect, url_for
import os
from core.utils import log_action, MongoJSONProvider
from core.middleware import login_required
from core.db import get_dev_updates_collection, get_items_collection, get_categories_collection, get_purchase_collection, get_inventory_log_collection, get_system_log_collection, get_notes_collection, get_subscriptions_collection
import subprocess
import importlib.metadata
from datetime import datetime
import json
from bson.objectid import ObjectId

developer_bp = Blueprint('developer', __name__)

@developer_bp.route('/log-client-error', methods=['POST'])
def log_client_error():
    data = request.json
    error_msg = data.get('error', 'Unknown Error')
    url = data.get('url', 'N/A')
    line = data.get('line', 'N/A')
    col = data.get('col', 'N/A')
    user_agent = request.headers.get('User-Agent', 'Unknown')
    device = "Mobile" if "Mobi" in user_agent else "Desktop"
    details = f"[BROWSER-{device}] {error_msg} at {url}:{line}:{col}"
    log_action("CLIENT_ERROR", details, send_push=False)
    print(f"ERROR: {details}")
    return jsonify({"success": True})

@developer_bp.route('/developer')
@login_required
def developer_portal():
    dev_updates_collection = get_dev_updates_collection()
    dev_updates = list(dev_updates_collection.find().sort("timestamp", -1))
    
    watchdog_active = False
    try:
        subprocess.check_output(["pgrep", "-f", "watchdog.sh"])
        watchdog_active = True
    except:
        watchdog_active = False

    stats = {"Python": 1100, "HTML/Jinja": 2400, "JavaScript": 350, "CSS": 150}
    total_lines = sum(stats.values())
    lang_percents = {k: round((v / total_lines) * 100, 1) for k, v in stats.items()}
    
    key_libs = ["Flask", "pymongo", "Flask-PyMongo", "pywebpush", "psutil", "requests", "python-dotenv"]
    libs = {}
    for lib in key_libs:
        try:
            libs[lib] = importlib.metadata.version(lib)
        except importlib.metadata.PackageNotFoundError:
            libs[lib] = "Installed"

    tech_files = {}
    for filename in ['robots.txt', 'sitemap.xml', 'manifest.json']:
        path = os.path.join(current_app.root_path, 'static', filename)
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

@developer_bp.route('/dev-updates/add', methods=['POST'])
@login_required
def add_dev_update():
    dev_updates_collection = get_dev_updates_collection()
    content = request.form.get('content')
    tag = request.form.get('tag', 'UPDATE')
    if content:
        dev_updates_collection.insert_one({
            "content": content,
            "tag": tag,
            "timestamp": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
        })
        flash("Development update posted!", "success")
    return redirect(url_for('developer.developer_portal'))

@developer_bp.route('/dev-updates/delete/<id>', methods=['POST'])
@login_required
def delete_dev_update(id):
    dev_updates_collection = get_dev_updates_collection()
    dev_updates_collection.delete_one({"_id": ObjectId(id)})
    flash("Update removed.", "info")
    return redirect(url_for('developer.developer_portal'))

@developer_bp.route('/developer/watchdog/start', methods=['POST'])
@login_required
def start_watchdog():
    try:
        subprocess.check_output(["pgrep", "-f", "watchdog.sh"])
        return jsonify({"success": True, "message": "Watchdog is already running."})
    except:
        script_path = os.path.join(current_app.root_path, "watchdog.sh")
        subprocess.Popen(["/bin/bash", script_path], 
                         stdout=open(os.devnull, 'w'), 
                         stderr=open(os.devnull, 'w'), 
                         start_new_session=True)
        log_action("WATCHDOG_START", "Developer started the system watchdog.")
        return jsonify({"success": True, "message": "Watchdog started successfully."})

@developer_bp.route('/developer/watchdog/stop', methods=['POST'])
@login_required
def stop_watchdog():
    try:
        subprocess.run(["pkill", "-f", "watchdog.sh"])
        log_action("WATCHDOG_STOP", "Developer stopped the system watchdog.")
        return jsonify({"success": True, "message": "Watchdog stopped."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@developer_bp.route('/developer/file/update', methods=['POST'])
@login_required
def update_tech_file():
    filename = request.form.get('filename')
    content = request.form.get('content')
    if filename in ['robots.txt', 'sitemap.xml', 'manifest.json']:
        path = os.path.join(current_app.root_path, 'static', filename)
        try:
            with open(path, 'w') as f:
                f.write(content)
            log_action("UPDATE_FILE", f"Developer modified {filename}")
            return jsonify({"success": True, "message": f"{filename} updated successfully!"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})
    return jsonify({"success": False, "message": "Invalid filename"})

@developer_bp.route('/developer/scan', methods=['POST'])
@login_required
def developer_scan():
    from scanner import WebsiteScanner
    base_url = "http://127.0.0.1:5000/"
    scanner = WebsiteScanner(base_url, cookies=request.cookies)
    results = scanner.run_scan()
    log_action("SYSTEM_SCAN", f"Developer performed a full system health scan. Found {len(results['broken_links'])} broken links and {len(results['vulnerabilities'])} vulnerabilities.")
    return jsonify(results)

@developer_bp.route('/developer/live-debug')
@login_required
def live_debug():
    return render_template('live_debug.html', role=session.get('role'))

@developer_bp.route('/developer/health-scanner')
@login_required
def health_scanner():
    return render_template('health_scanner.html', role=session.get('role'))

@developer_bp.route('/developer/docs')
@login_required
def developer_docs():
    return render_template('documentation.html', role=session.get('role'))

@developer_bp.route('/developer/logs')
@login_required
def stream_logs():
    try:
        log_path = os.path.join(current_app.root_path, 'app_output.log')
        with open(log_path, 'r') as f:
            lines = f.readlines()
            filtered = [line for line in lines if "/developer/logs" not in line and "/system-info" not in line and "/latest-log" not in line]
            return "".join(filtered[-100:])
    except:
        return "Log file not found."

@developer_bp.route('/developer/backup')
@login_required
def developer_backup():
    try:
        data = {
            "items": list(get_items_collection().find({}, {'_id': 0})),
            "categories": list(get_categories_collection().find({}, {'_id': 0})),
            "purchase": list(get_purchase_collection().find({}, {'_id': 0})),
            "inventory_log": list(get_inventory_log_collection().find({}, {'_id': 0})),
            "system_logs": list(get_system_log_collection().find({}, {'_id': 0})),
            "notes": list(get_notes_collection().find({}, {'_id': 0})),
            "subscriptions": list(get_subscriptions_collection().find({}, {'_id': 0})),
            "dev_updates": list(get_dev_updates_collection().find({}, {'_id': 0}))
        }
        filename = f"xpider_backup_{datetime.now().strftime('%Y%m%d')}.json"
        return Response(
            current_app.json.dumps(data, indent=4),
            mimetype='application/json',
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        print(f"[BACKUP-ERROR] {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@developer_bp.route('/developer/seed-data', methods=['POST'])
@login_required
def seed_test_data():
    try:
        script_path = os.path.join(current_app.root_path, "generate_sample_data.py")
        # Run with current environment's python
        import sys
        subprocess.run([sys.executable, script_path], check=True)
        log_action("SEED_DATA", "Developer seeded the database with test data.")
        return jsonify({"success": True, "message": "Database seeded with 50+ test items and sales history!"})
    except Exception as e:
        print(f"[SEED-ERROR] {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@developer_bp.route('/developer/server/restart', methods=['POST'])
@login_required
def server_restart():
    log_action("SERVER_RESTART", "Developer triggered remote server restart.")
    import sys
    import time
    import eventlet
    
    def perform_restart():
        time.sleep(1)
        script_path = os.path.join(current_app.root_path, "app.py")
        py_path = sys.executable
        cwd = current_app.root_path
        log_path = os.path.join(cwd, 'app_output.log')
        cmd = f"sleep 2 && fuser -k 5000/tcp ; nohup {py_path} {script_path} >> {log_path} 2>&1 &"        
        subprocess.Popen(['/bin/bash', '-c', cmd], cwd=cwd, start_new_session=True)
        os._exit(0)
    
    eventlet.spawn_after(0.5, perform_restart)
    return jsonify({"success": True, "message": "Server rebooting... reconnecting in 5s."})

@developer_bp.route('/developer/server/toggle-debug', methods=['POST'])
@login_required
def toggle_debug():
    env_path = os.path.join(current_app.root_path, '.env')
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
    os.environ["FLASK_DEBUG"] = 'true' if new_debug else 'false'
    log_action("DEBUG_TOGGLE", f"Debug Mode set to {new_debug}")
    return server_restart()
