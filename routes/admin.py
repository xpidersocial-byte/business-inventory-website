from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response, current_app
from core.utils import get_site_config, log_action, send_email_notification, MongoJSONProvider
from core.middleware import login_required, role_required, get_cashier_permissions, get_owner_permissions
from core.db import get_users_collection, get_settings_collection, get_items_collection, get_categories_collection, get_menus_collection, get_purchase_collection, get_sales_collection, get_inventory_log_collection, get_system_log_collection, get_notes_collection
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import os
import json
import random
import re
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/accounts')
@login_required
def admin_accounts():
    if session.get('role') != 'owner':
        flash("Access Denied.", "danger")
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/admin/permissions/update', methods=['POST'])
@login_required
@role_required('owner')
def update_permissions():
    settings_collection = get_settings_collection()
    fields = [
        "dashboard", "pos", "items_master", "sales_ledger", "sales_summary", 
        "restock", "bulletin_board", "legend", "developer_portal", "live_debug", 
        "health_scanner", "admin_accounts", "general_setup", "system_logs",
        "setup_identity", "setup_localization", "setup_logic", "setup_users",
        "setup_categories", "setup_themes", "setup_advanced", "setup_assets", 
        "setup_backup", "setup_danger_zone", "setup_smtp", "setup_notifications"
    ]
    new_perms = {field: (request.form.get(field) == 'on') for field in fields}
    settings_collection.update_one({"type": "cashier_permissions"}, {"$set": new_perms}, upsert=True)
    log_action("UPDATE_PERMISSIONS", "Owner updated cashier access levels.")
    flash("Cashier permissions updated successfully!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/admin/owner-permissions/update', methods=['POST'])
@login_required
@role_required('owner')
def update_owner_permissions():
    settings_collection = get_settings_collection()
    fields = [
        "dashboard", "pos", "items_master", "sales_ledger", "sales_summary", 
        "restock", "bulletin_board", "legend", "developer_portal", "live_debug", 
        "health_scanner", "admin_accounts", "general_setup", "system_logs",
        "setup_identity", "setup_localization", "setup_logic", "setup_users",
        "setup_categories", "setup_themes", "setup_advanced", "setup_assets", 
        "setup_backup", "setup_danger_zone", "setup_smtp", "setup_notifications"
    ]
    new_perms = {field: (request.form.get(field) == 'on') for field in fields}
    settings_collection.update_one({"type": "owner_permissions"}, {"$set": new_perms}, upsert=True)
    log_action("UPDATE_OWNER_PERMISSIONS", "Owner updated global access levels for Owners.")
    flash("Owner access control updated successfully!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/general-setup')
@login_required
@role_required('owner')
def general_setup():
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/profile/update', methods=['POST'])
@login_required
@role_required('owner')
def update_profile():
    settings_collection = get_settings_collection()
    # Surgical update: fetch existing config first
    existing_config = get_site_config()
    form_section = request.form.get('form_id') # New sentinel to know which section is being saved
    
    update_fields = {}
    
    # Text/Select Fields - Only update if present in form
    for key in ["business_name", "business_icon", "currency_symbol", "footer_text", 
                "contact_address", "contact_phone", "contact_email", "timezone", 
                "date_format", "time_format", "social_facebook", "social_twitter", 
                "social_instagram", "custom_head_scripts", "custom_body_scripts", 
                "smtp_host", "smtp_user", "smtp_password", 
                "smtp_sender", "email_recipient_list"]:
        if key in request.form:
            update_fields[key] = request.form.get(key)
    
    # Enforce Facebook theme globally
    update_fields["default_theme"] = "facebook"

    # Numeric Fields
    def clean_num(val, default=0, is_int=False):
        if not val or str(val).strip() == "": return default
        try:
            return int(val) if is_int else float(val)
        except:
            return default

    if "low_stock_threshold" in request.form:
        update_fields["low_stock_threshold"] = clean_num(request.form.get('low_stock_threshold'), 5, True)
    if "tax_rate" in request.form:
        update_fields["tax_rate"] = clean_num(request.form.get('tax_rate'), 0.0)
    if "smtp_port" in request.form:
        update_fields["smtp_port"] = clean_num(request.form.get('smtp_port'), 587, True)
    
    # Checkbox Fields - Logic: if they belong to this section but are NOT ON, then they are OFF
    # Otherwise, don't touch them if we're in another section.

    # 1. Identity Section Checkboxes
    if form_section == 'identity':
        update_fields["maintenance_mode"] = request.form.get('maintenance_mode') == 'on'

    # 2. SMTP Section Checkboxes
    if form_section == 'smtp':
        update_fields["smtp_use_tls"] = request.form.get('smtp_use_tls') == 'on'
        update_fields["smtp_use_ssl"] = request.form.get('smtp_use_ssl') == 'on'

    # 3. Notification Section Checkboxes
    if form_section == 'notifications':
        notif_keys = [
            "email_notif_stock_in", "email_notif_stock_out", "email_notif_low_stock", 
            "email_notif_sales", "email_notif_login", "email_notif_profile", 
            "email_notif_inventory", "email_notif_bulletin"
        ]
        for key in notif_keys:
            update_fields[key] = request.form.get(key) == 'on'

    if update_fields:
        update_fields["updated_at"] = datetime.now()
        settings_collection.update_one({"type": "general"}, {"$set": update_fields}, upsert=True)
        log_action("UPDATE_CONFIG", f"Updated settings section: {form_section or 'generic'}")
    
    flash("Settings updated successfully!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/login-bg/update', methods=['POST'])
@login_required
@role_required('owner')
def update_login_bg():
    settings_collection = get_settings_collection()
    file = request.files.get('login_bg')
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        new_filename = f"login_bg_{int(datetime.now().timestamp())}.{ext}"
        target_path = os.path.join(current_app.root_path, 'static', 'images', new_filename)
        file.save(target_path)
        settings_collection.update_one({"type": "general"}, {"$set": {"login_background": f"images/{new_filename}"}})
        log_action("UPDATE_LOGIN_BG", "Updated login page background image.")
        flash("Login background updated!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/category/add', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('name')
    if name:
        if not get_categories_collection().find_one({"name": name}):
            get_categories_collection().insert_one({"name": name})
            log_action("ADD_CATEGORY", f"Added category: {name}")
            flash(f"Category '{name}' added!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/category/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_category(id):
    try:
        oid = ObjectId(id)
    except:
        return jsonify({"success": False, "error": "Invalid ID format"}), 400

    cat = get_categories_collection().find_one({"_id": oid})
    if cat:
        get_categories_collection().delete_one({"_id": oid})
        log_action("DELETE_CATEGORY", f"Deleted category: {cat['name']}")
        flash("Category deleted.", "info")
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True})
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/user/add', methods=['POST'])
@login_required
@role_required('owner')
def add_user():
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role', 'cashier')
    if email and password:
        if not get_users_collection().find_one({"email": email}):
            get_users_collection().insert_one({"email": email, "password": password, "role": role})
            log_action("ADD_USER", f"Created user: {email} ({role})")
            flash(f"User '{email}' created successfully!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/user/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_user(id):
    try:
        oid = ObjectId(id)
    except:
        return jsonify({"success": False, "error": "Invalid ID format"}), 400

    user = get_users_collection().find_one({"_id": oid})
    if user:
        if user['email'] == 'admin@inventory.com':
            flash("Cannot delete the main admin account!", "danger")
            if request.is_json or 'application/json' in request.headers.get('Accept', ''):
                return jsonify({"success": False, "message": "Cannot delete main admin"}), 403
        else:
            get_users_collection().delete_one({"_id": oid})
            log_action("DELETE_USER", f"Deleted user: {user['email']}")
            flash("User deleted.", "info")
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True})
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/user/edit/<id>', methods=['POST'])
@login_required
@role_required('owner')
def edit_user(id):
    user = get_users_collection().find_one({"_id": ObjectId(id)})
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('auth.profile', tab='settings'))

    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')
    verification_code = request.form.get('verification_code')

    is_protected = user.get('role') == 'owner' or user.get('email') == 'admin@inventory.com'
    if is_protected or role == 'owner':
        stored_code = session.get('auth_code')
        expiry_str = session.get('auth_code_expiry')
        v_code = str(verification_code).strip() if verification_code else ""
        if not stored_code or not expiry_str or datetime.now() > datetime.fromisoformat(expiry_str) or v_code != stored_code:
            flash("Security authorization failed or expired. Please send code to email.", "danger")
            return redirect(url_for('auth.profile', tab='settings'))
        session.pop('auth_code', None); session.pop('auth_code_expiry', None)

    update_data = {}
    if email: update_data['email'] = email
    if password: update_data['password'] = password
    if role: update_data['role'] = role

    if update_data:
        get_users_collection().update_one({"_id": ObjectId(id)}, {"$set": update_data})
        log_action("EDIT_USER_ADMIN", f"Admin updated account for: {user['email']}")
        flash(f"Account for {user['email']} updated!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/menu/add', methods=['POST'])
@login_required
@role_required('owner')
def add_menu():
    name = request.form.get('name')
    if name:
        if not get_menus_collection().find_one({"name": name}):
            # Set order to end of list
            last_menu = get_menus_collection().find_one(sort=[("order", -1)])
            order = (last_menu.get('order', 0) + 1) if last_menu else 1
            get_menus_collection().insert_one({"name": name, "order": order})
            log_action("ADD_MENU", f"Added menu: {name}")
            flash(f"Menu '{name}' created!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/menu/reorder', methods=['POST'])
@login_required
@role_required('owner')
def reorder_menus():
    data = request.json
    order_list = data.get('order', []) # List of menu IDs in new order
    if order_list:
        menus_col = get_menus_collection()
        for index, menu_id in enumerate(order_list):
            menus_col.update_one({"_id": ObjectId(menu_id)}, {"$set": {"order": index}})
        return jsonify({"success": True})
    return jsonify({"success": False}), 400

@admin_bp.route('/settings/menu/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_menu(id):
    try:
        oid = ObjectId(id)
    except:
        return jsonify({"success": False, "error": "Invalid ID format"}), 400

    menu = get_menus_collection().find_one({"_id": oid})
    if menu:
        get_menus_collection().delete_one({"_id": oid})
        log_action("DELETE_MENU", f"Deleted menu: {menu['name']}")
        flash("Menu deleted.", "info")
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True})
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/menu/thresholds', methods=['POST'])
@login_required
def update_menu_thresholds():
    data = request.json
    type_ = data.get('type')
    warning = int(data.get('warning', 10))
    low = int(data.get('low', 5))
    
    if type_ == 'global':
        get_settings_collection().update_one(
            {"type": "general"}, 
            {"$set": {"warning_threshold": warning, "low_stock_threshold": low}},
            upsert=True
        )
    else:
        menu_id = data.get('id')
        if menu_id:
            get_menus_collection().update_one(
                {"_id": ObjectId(menu_id)},
                {"$set": {"warning_threshold": warning, "low_stock_threshold": low}}
            )
            
    log_action("UPDATE_THRESHOLDS", f"Updated stock thresholds for {type_}")
    return jsonify({"success": True})

@admin_bp.route('/settings/data/clear', methods=['POST'])
@login_required
@role_required('owner')
def clear_all_data():
    # Clear all business-related collections
    from core.db import (
        get_items_collection, get_purchase_collection, get_sales_collection,
        get_inventory_log_collection, get_system_log_collection,
        get_categories_collection, get_notes_collection, get_undo_logs_collection,
        get_menus_collection, get_todos_collection, get_subscriptions_collection
    )
    
    get_items_collection().delete_many({})
    get_purchase_collection().delete_many({})
    get_sales_collection().delete_many({})
    get_inventory_log_collection().delete_many({})
    get_system_log_collection().delete_many({})
    get_categories_collection().delete_many({})
    get_notes_collection().delete_many({})
    get_undo_logs_collection().delete_many({})
    get_menus_collection().delete_many({})
    get_todos_collection().delete_many({})
    get_subscriptions_collection().delete_many({})
    
    log_action("CLEAR_DATABASE", "Owner wiped all business records including summary sales, categories, and logs.")
    flash("The database has been fully purged! Only user accounts and core settings remain.", "warning")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/backup/download')
@login_required
@role_required('owner')
def download_backup():
    try:
        data = {
            "items": list(get_items_collection().find({}, {'_id': 0})),
            "categories": list(get_categories_collection().find({}, {'_id': 0})),
            "purchase": list(get_purchase_collection().find({}, {'_id': 0})),
            "sales": list(get_sales_collection().find({}, {'_id': 0})),
            "inventory_log": list(get_inventory_log_collection().find({}, {'_id': 0})),
            "system_logs": list(get_system_log_collection().find({}, {'_id': 0})),
            "notes": list(get_notes_collection().find({}, {'_id': 0})),
            "users": list(get_users_collection().find({}, {'_id': 0})),
            "settings": list(get_settings_collection().find({}, {'_id': 0})),
            "menus": list(get_menus_collection().find({}, {'_id': 0}))
        }
        filename = f"xpider_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        from flask import json
        return Response(json.dumps(data, indent=4), mimetype='application/json', headers={"Content-disposition": f"attachment; filename={filename}"})
    except Exception as e:
        flash(f"Backup failed: {str(e)}", "danger")
        return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/backup/import', methods=['POST'])
@login_required
@role_required('owner')
def import_backup():
    auth_code = request.form.get('import_auth_code')
    stored_code = session.get('auth_code')
    expiry_str = session.get('auth_code_expiry')
    
    if not stored_code or not expiry_str or datetime.now() > datetime.fromisoformat(expiry_str) or str(auth_code).strip() != stored_code:
        flash("Security authorization failed or expired. Please request a new code.", "danger")
        return redirect(url_for('auth.profile', tab='settings'))
    
    file = request.files.get('backup_file')
    if not file or not file.filename.endswith('.json'):
        flash("Invalid file format. Please upload a .json file.", "danger")
        return redirect(url_for('auth.profile', tab='settings'))
        
    try:
        data = json.load(file)
        expected_keys = ["items", "sales", "purchase", "categories", "inventory_log"]
        if not any(k in data for k in expected_keys):
            raise ValueError("JSON file does not match expected backup schema.")
            
        session.pop('auth_code', None)
        session.pop('auth_code_expiry', None)
        
        collections_map = {
            "categories": get_categories_collection(),
            "items": get_items_collection(),
            "purchase": get_purchase_collection(),
            "sales": get_sales_collection(),
            "inventory_log": get_inventory_log_collection(),
            "system_logs": get_system_log_collection(),
            "notes": get_notes_collection(),
            "menus": get_menus_collection()
        }
        
        for key, coll in collections_map.items():
            if key in data and isinstance(data[key], list):
                coll.delete_many({})
                records = data[key]
                for record in records:
                    record.pop("_id", None)
                if records:
                    coll.insert_many(records)
                    
        log_action("IMPORT_DATABASE", "Owner successfully imported system data from JSON.")
        flash("System Data Imported Successfully!", "success")
        
    except Exception as e:
        flash(f"Import failed: {str(e)}", "danger")

    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/admin/send-auth-code', methods=['POST'])
@login_required
@role_required('owner')
def send_auth_code():
    code = str(random.randint(100000, 999999))
    session['auth_code'] = code
    session['auth_code_expiry'] = (datetime.now() + timedelta(minutes=10)).isoformat()
    recipient = "bejasadhev@gmail.com"
    success = send_email_notification("Owner Security Authorization Code", f"SECURITY ALERT: Your Authorization Code is: {code}", override_recipient=recipient)
    return jsonify({"success": success, "message": f"Verification code sent to {recipient}" if success else "Failed to send email."})
@admin_bp.route('/admin/database-stats')
@login_required
@role_required('owner')
def database_stats():
    from extensions import mongo
    db = mongo.db
    stats = {}
    
    try:
        # Get DB Stats
        db_stats = db.command("dbStats")
        
        # Format sizes to human readable
        def format_size(size_bytes):
            if size_bytes < 1024: return f"{size_bytes} B"
            elif size_bytes < 1024**2: return f"{size_bytes/1024:.2f} KB"
            elif size_bytes < 1024**3: return f"{size_bytes/1024**2:.2f} MB"
            else: return f"{size_bytes/1024**3:.2f} GB"

        stats['db_name'] = db.name
        stats['data_size'] = format_size(db_stats.get('dataSize', 0))
        stats['storage_size'] = format_size(db_stats.get('storageSize', 0))
        stats['index_size'] = format_size(db_stats.get('indexSize', 0))
        stats['objects_count'] = db_stats.get('objects', 0)
        stats['collections_count'] = db_stats.get('collections', 0)
        
        # Get collection specific counts
        collections = []
        for coll_name in sorted(db.list_collection_names()):
            count = db[coll_name].count_documents({})
            collections.append({
                "name": coll_name,
                "count": count
            })
        stats['collections'] = collections
        
        # Connection host info
        uri = os.getenv("MONGO_URI", "")
        if "localhost" in uri or "127.0.0.1" in uri:
            stats['connection_host'] = "mongodb://localhost:27017"
            stats['cluster_type'] = "Local Community Edition"
        elif "@" in uri:
            prefix, rest = uri.split("@", 1)
            masked_prefix = prefix.split("://")[0] + "://user:****"
            stats['connection_host'] = masked_prefix + "@" + rest.split("?")[0]
            stats['cluster_type'] = "MongoDB Atlas (Cloud)"
        else:
            stats['connection_host'] = uri or "Local/Managed"
            stats['cluster_type'] = "Primary"

        # Get server version info
        try:
            server_info = db.client.server_info()
            stats['server_version'] = server_info.get('version', 'Unknown')
        except:
            stats['server_version'] = 'Unknown'

        stats['status'] = "Connected"
    except Exception as e:
        stats['status'] = "Error"
        stats['error'] = str(e)
        
    return jsonify(stats)

@admin_bp.route('/admin/test-email', methods=['POST'])
@login_required
@role_required('owner')
def test_email():
    import smtplib
    from email.mime.text import MIMEText
    from extensions import socketio
    from core.utils import get_site_config
    
    data = request.json or {}
    recipient = data.get('recipient')
    
    config = get_site_config()
    if not recipient:
        recipient = config.get('contact_email')
    
    if not recipient:
        return jsonify({"success": False, "message": "No contact email configured to receive the test."})

    def emit_log(msg, type="info"):
        socketio.emit('smtp_log', {'message': msg, 'type': type})

    try:
        host = config.get('smtp_host')
        port = int(config.get('smtp_port', 587))
        user = config.get('smtp_user')
        passw = config.get('smtp_password')
        sender = config.get('smtp_sender') or user
        use_tls = config.get('smtp_use_tls', True)
        use_ssl = config.get('smtp_use_ssl', False)

        emit_log(f"Initializing connection to {host}:{port}...")
        
        # Connection
        if use_ssl:
            emit_log("Using SSL connection...")
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            if use_tls:
                emit_log("STARTTLS initiated...")
                server.starttls()

        emit_log(f"Authenticating as {user}...")
        server.login(user, passw)
        emit_log("Login successful!")

        emit_log(f"Preparing payload for {recipient}...")
        msg = MIMEText("This is a real-time SMTP test from FBIHM Inventory.")
        msg['Subject'] = "FBIHM: SMTP Progress Test"
        msg['From'] = sender
        msg['To'] = recipient

        server.send_message(msg)
        emit_log("Message sent successfully!")
        
        try:
            server.quit()
        except:
            pass

        emit_log("SMTP Test Completed.", type="success")
        return jsonify({"success": True, "message": "Test email sent successfully!"})

    except Exception as e:
        error_msg = str(e)
        emit_log(f"SMTP Error: {error_msg}", type="error")
        return jsonify({"success": False, "message": f"SMTP Error: {error_msg}"})



# ── Notification API ─────────────────────────────────────────────────────────
@admin_bp.route('/api/notifications')
@login_required
def get_notifications():
    """Returns aggregated in-app notifications: low stock + unread bulletins."""
    notifications = []
    try:
        config = get_site_config()
        threshold = config.get('low_stock_threshold', 5)
        
        user_email = session.get('email', '')
        users_col = get_users_collection()
        user = users_col.find_one({"email": user_email}) or {}
        read_notif_ids = user.get('read_notif_ids', [])

        # 1. Low-stock / out-of-stock items
        # Filter out items already dismissed in this session
        dismissed_notifs = session.get('dismissed_notifs', [])
        items_col = get_items_collection()
        low_items = list(items_col.find(
            {"active": {"$ne": False}, "_id": {"$nin": [ObjectId(id) for id in dismissed_notifs if ObjectId.is_valid(id)]}, "stock": {"$lte": threshold}},
            {"name": 1, "stock": 1}
        ).limit(50))

        unread_count = 0
        for item in low_items:
            stock = item.get('stock', 0)
            item_id = str(item['_id'])
            is_read = item_id in read_notif_ids
            if not is_read:
                unread_count += 1
                
            if stock == 0:
                notifications.append({
                    "id": item_id + "_stock",
                    "item_id": item_id,
                    "title": "Out of Stock",
                    "body": f"{item['name']} has run out of stock.",
                    "icon": "bi-exclamation-circle-fill",
                    "color": "#dc3545",
                    "time": "Now",
                    "type": "stock",
                    "is_read": is_read,
                    "url": f"/restock?item_id={item_id}"
                })
            else:
                notifications.append({
                    "id": item_id + "_low",
                    "item_id": item_id,
                    "title": "Low Stock Warning",
                    "body": f"{item['name']} — only {stock} unit(s) left.",
                    "icon": "bi-exclamation-triangle-fill",
                    "color": "#fd7e14",
                    "time": "Now",
                    "type": "stock",
                    "is_read": is_read,
                    "url": f"/restock?item_id={item_id}"
                })

        # 2. Bulletin notes (show both read/unread for feed)
        notes_col = get_notes_collection()
        recent_notes = list(notes_col.find(
            {"status": {"$ne": "done"}},
            {"title": 1, "created_at": 1, "read_by": 1}
        ).sort("created_at", -1).limit(20))

        for note in recent_notes:
            note_id = str(note['_id'])
            read_by_list = note.get('read_by', [])
            is_read = user_email in read_by_list
            if not is_read:
                unread_count += 1
                
            notifications.append({
                "id": note_id + "_note",
                "item_id": note_id,
                "title": "Bulletin Board",
                "body": note.get('title', 'New bulletin notice'),
                "icon": "bi-clipboard-data",
                "color": "#f02849",
                "time": str(note.get('created_at', '')),
                "type": "bulletin",
                "is_read": is_read,
                "url": "/bulletin"
            })

        # Sort notifications so unread are at the top
        notifications = sorted(notifications, key=lambda x: x['is_read'])

        # 3. Sidebar Category Counts (Activity since last visit)
        last_views = user.get('last_views', {})

        
        # Helper to get the correct comparison time
        def get_comp_time(key):
            val = last_views.get(key)
            if isinstance(val, str):
                try: return datetime.fromisoformat(val)
                except: pass
            return val if isinstance(val, datetime) else datetime(2020, 1, 1)

        ts_items = get_comp_time('items')
        ts_sales = get_comp_time('sales')
        ts_restocks = get_comp_time('restocks')
        ts_legend = get_comp_time('legend')

        items_col = get_items_collection()
        purchase_col = get_purchase_collection()
        log_col = get_inventory_log_collection()
        
        # New Items since last visit
        new_items_count = items_col.count_documents({
            "created_at": {"$gt": ts_items}
        })
        
        # New Sales (using ISO format for sorting)
        last_sales_str = ts_sales.strftime('%Y-%m-%dT%H:%M:%S')
        new_sales_count = purchase_col.count_documents({
            "date": {"$gt": last_sales_str}
        })
        
        # New Restocks
        last_restock_str = ts_restocks.strftime('%Y-%m-%dT%H:%M:%S')
        new_restocks_count = log_col.count_documents({
            "type": {"$in": ["IN", "DAMAGE"]},
            "timestamp": {"$gt": last_restock_str}
        })
        
        # New Bulletins (notes created after last visit to /bulletin)
        ts_bulletins = get_comp_time('bulletins')
        new_bulletins_count = notes_col.count_documents({
            "status": {"$ne": "done"},
            "created_at": {"$gt": ts_bulletins}
        })

        # Legend Alerts (Warning or Low) - Now ONLY shows unread transitions
        config = get_site_config()
        warn_threshold = config.get('warning_threshold', 10)
        
        # All items currently in Warning or Low state (including Out of Stock)
        current_alerts = list(items_col.find({
            "active": {"$ne": False},
            "stock": {"$lte": warn_threshold} 
        }, {"name": 1}))
        
        legend_alerts = 0
        if current_alerts:
            # For each alerting item, check if there was ANY activity since last visit
            # Using ISO format for correct lexicographical sorting: %Y-%m-%dT%H:%M:%S
            last_legend_str = ts_legend.strftime('%Y-%m-%dT%H:%M:%S')
            for alert_item in current_alerts:
                has_new_activity = log_col.find_one({
                    "item_name": alert_item['name'],
                    "type": {"$in": ["OUT", "DAMAGE", "ADJUST", "EXPIRED"]},
                    "timestamp": {"$gt": last_legend_str}
                })
                if has_new_activity:
                    legend_alerts += 1

    except Exception as e:
        print(f"[Notif Error] {e}")
        notifications = []

    # The global unread_count is the sum of stock alerts + bulletins + sidebar activity
    global_unread = unread_count + new_sales_count + new_restocks_count + new_items_count + new_bulletins_count + legend_alerts

    return jsonify({
        "unread_count": global_unread,
        "notifications": notifications,
        "sidebar": {
            "dashboard": 0,
            "items": new_items_count,
            "sales": new_sales_count,
            "restocks": new_restocks_count,
            "sales_summary": 0,
            "legend": legend_alerts,
            "bulletins": new_bulletins_count,
            "settings": 0
        }
    })


@admin_bp.route('/api/notifications/mark-view', methods=['POST'])
@login_required
def mark_notification_view():
    """Update last_views timestamp for a specific view (sidebar section)."""
    try:
        data = request.get_json() or {}
        view = data.get('view')
        user_email = session.get('email', '')
        
        if not user_email or not view:
            return jsonify({"success": False}), 400
            
        now = datetime.now()
        get_users_collection().update_one(
            {"email": user_email},
            {"$set": {f"last_views.{view}": now}}
        )
        return jsonify({"success": True})
    except Exception as e:
        print(f"[Mark View Error] {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route('/api/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    """Mark all notifications as read for the current user."""
    try:
        user_email = session.get('email', '')
        if not user_email: return jsonify({"success": False}), 401
        
        # 1. Mark bulletins as read
        get_notes_collection().update_many(
            {"status": {"$ne": "deleted"}},
            {"$addToSet": {"read_by": user_email}}
        )
        
        # 2. Mark low stock as read
        config = get_site_config()
        threshold = config.get('low_stock_threshold', 5)
        low_ids = [str(i['_id']) for i in get_items_collection().find({"active": {"$ne": False}, "stock": {"$lte": threshold}}, {"_id": 1})]
        
        if low_ids:
            get_users_collection().update_one(
                {"email": user_email},
                {"$addToSet": {"read_notif_ids": {"$each": low_ids}}}
            )
        
        # 3. Mark all sidebar activity as read (update last_views)
        now = datetime.now()
        get_users_collection().update_one(
            {"email": user_email},
            {"$set": {
                "last_views.items": now,
                "last_views.sales": now,
                "last_views.restocks": now,
                "last_views.legend": now,
                "last_views.bulletins": now
            }}
        )
        
    except Exception as e:
        print(f"[Mark Read Error] {e}")
    return jsonify({"success": True})


@admin_bp.route('/api/notifications/dismiss', methods=['POST'])
@login_required
def dismiss_notification():
    """Add an item ID to the session's dismissed list."""
    data = request.get_json() or {}
    item_id = data.get('item_id')
    if item_id:
        if 'dismissed_notifs' not in session:
            session['dismissed_notifs'] = []
        if item_id not in session['dismissed_notifs']:
            session['dismissed_notifs'].append(item_id)
            session.modified = True
    return jsonify({"success": True})


@admin_bp.route('/api/notifications/mark-one', methods=['POST'])
@login_required
def mark_one_notification_read():
    """Mark a single bulletin note as read by its ID."""
    data = request.get_json() or {}
    note_id = data.get('note_id')
    notif_type = data.get('type', '')
    if notif_type == 'bulletin' and note_id:
        try:
            user_email = session.get('email', '')
            notes_col = get_notes_collection()
            notes_col.update_one(
                {"_id": ObjectId(note_id)},
                {"$addToSet": {"read_by": user_email}}
            )
        except Exception as e:
            print(f"[Mark One Read Error] {e}")
    return jsonify({"success": True})
