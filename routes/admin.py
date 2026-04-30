from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response, current_app
from core.utils import safe_object_id, get_site_config, log_action, send_email_notification, MongoJSONProvider, trigger_notification, reschedule_periodic_jobs
from core.middleware import login_required, role_required, get_cashier_permissions, get_owner_permissions
from core.db import get_users_collection, get_settings_collection, get_items_collection, get_categories_collection, get_menus_collection, get_purchase_collection, get_sales_collection, get_inventory_log_collection, get_system_log_collection, get_notes_collection
from bson.objectid import ObjectId
from datetime import datetime, timedelta, timezone
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
    trigger_notification("perms_update", "Cashier Roles Updated", "Global permissions for Cashier staff have been modified.", priority="INFO")
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
    trigger_notification("perms_update", "Owner Roles Updated", "Global access control for Owner accounts has been modified.", priority="CRITICAL")
    flash("Owner access control updated successfully!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/general-setup')
@login_required
@role_required('owner')
def general_setup():
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/admin/settings/general/update', methods=['POST'])
@login_required
@role_required('owner')
def update_general_settings():
    """Handles the 'Save All' form from general_setup.html"""
    settings_collection = get_settings_collection()
    upd = {}
    
    # Standard field extraction
    for key in request.form:
        if key in ['verification_code', 'section']: continue
        val = request.form.get(key)
        if val == 'on':
            upd[key] = True
        else:
            upd[key] = val

    # Explicitly handle common switches that might be missing if unchecked
    switches = [
        'maintenance_mode', 'smtp_use_tls', 'smtp_use_ssl',
        'email_notif_stock_in', 'email_notif_stock_out', 'email_notif_low_stock',
        'email_notif_sales', 'email_notif_login', 'email_notif_profile',
        'email_notif_inventory', 'email_notif_bulletin'
    ]
    for s in switches:
        if s not in request.form:
            upd[s] = False

    upd['updated_at'] = datetime.now(timezone.utc)
    settings_collection.update_one({"type": "general"}, {"$set": upd}, upsert=True)
    
    # Reload background jobs if SMTP or Notif changed
    try:
        reschedule_periodic_jobs(current_app.scheduler)
    except: pass

    log_action("UPDATE_GLOBAL_SETTINGS", "Owner updated system-wide configuration via General Setup.")
    trigger_notification("settings_update", "System Config Updated", "General system settings have been modified.", priority="CRITICAL")
    flash("General settings updated successfully!", "success")
    return redirect(url_for('admin.general_setup'))

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
        trigger_notification("settings_update", "Configuration Changed", f"The '{form_section or 'general'}' system configuration was updated.", {"section": form_section}, priority="INFO")
    
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
    role = session.get('role', 'cashier')
    branch_id = session.get('branch_id')
    
    if name:
        query = {"name": name}
        # If not global, scope the name check to this branch
        if role != 'owner' or branch_id:
            query["branch_id"] = {"$in": [branch_id, safe_object_id(branch_id)] if branch_id else [None]}

        if not get_categories_collection().find_one(query):
            get_categories_collection().insert_one({
                "name": name,
                "branch_id": safe_object_id(branch_id) if branch_id else None
            })
            log_action("ADD_CATEGORY", f"Added category: {name}")
            trigger_notification("settings_update", "New Category Added", f"Category '{name}' was added to the system.", priority="INFO")
            flash(f"Category '{name}' added!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/category/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_category(id):
    cat = get_categories_collection().find_one({"_id": ObjectId(id)})
    if cat:
        get_categories_collection().delete_one({"_id": ObjectId(id)})
        log_action("DELETE_CATEGORY", f"Deleted category: {cat['name']}")
        trigger_notification("settings_update", "Category Deleted", f"Category '{cat['name']}' was removed from the system.", priority="WARNING")
        flash("Category deleted.", "info")
    section = request.form.get('section', 'cats-menus')
    return redirect(url_for('auth.profile', tab='settings', section=section))

@admin_bp.route('/settings/user/add', methods=['POST'])
@login_required
@role_required('owner')
def add_user():
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role', 'cashier')
    branch_id = request.form.get('branch_id')
    if email and password:
        if not get_users_collection().find_one({"email": email}):
            from core.utils import safe_object_id, hash_password
            get_users_collection().insert_one({
                "email": email, 
                "password": hash_password(password), 
                "role": role,
                "branch_id": safe_object_id(branch_id) if branch_id else None
            })
            log_action("ADD_USER", f"Created user: {email} ({role})")
            trigger_notification("user_added", "Account Created", f"A new {role} account for {email} was created.", {"email": email}, priority="SUCCESS")
            flash(f"User '{email}' created successfully!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/user/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_user(id):
    user = get_users_collection().find_one({"_id": ObjectId(id)})
    if user:
        if user['email'] == 'admin@inventory.com':
            flash("Cannot delete the main admin account!", "danger")
        else:
            get_users_collection().delete_one({"_id": ObjectId(id)})
            log_action("DELETE_USER", f"Deleted user: {user['email']}")
            trigger_notification("user_deleted", "Account Removed", f"The user account for {user['email']} was deleted.", priority="WARNING")
            flash("User deleted.", "info")
    section = request.form.get('section', 'user-mgmt')
    return redirect(url_for('auth.profile', tab='settings', section=section))

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
    branch_id = request.form.get('branch_id')
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
    if password: 
        from core.utils import safe_object_id, hash_password
        update_data['password'] = hash_password(password)
    if role: update_data['role'] = role
    if branch_id: update_data['branch_id'] = safe_object_id(branch_id) if branch_id else None

    if update_data:
        get_users_collection().update_one({"_id": ObjectId(id)}, {"$set": update_data})
        log_action("EDIT_USER_ADMIN", f"Admin updated account for: {user['email']}")
        trigger_notification("user_updated", "Account Updated", f"Administrative changes were made to the account for {user['email']}.", {"email": user['email']}, priority="INFO")
        flash(f"Account for {user['email']} updated!", "success")
    return redirect(url_for('auth.profile', tab='settings'))

@admin_bp.route('/settings/menu/add', methods=['POST'])
@login_required
@role_required('owner')
def add_menu():
    role = session.get('role', 'cashier')
    branch_id = session.get('branch_id')
    
    name = request.form.get('name')
    if name:
        query = {"name": name}
        if role != 'owner' or branch_id:
            query["branch_id"] = {"$in": [branch_id, safe_object_id(branch_id)] if branch_id else [None]}

        if not get_menus_collection().find_one(query):
            # Set order to end of list within this branch
            order_query = {}
            if role != 'owner' or branch_id:
                order_query["branch_id"] = {"$in": [branch_id, safe_object_id(branch_id)] if branch_id else [None]}
                
            last_menu = get_menus_collection().find_one(order_query, sort=[("order", -1)])
            order = (last_menu.get('order', 0) + 1) if last_menu else 1
            get_menus_collection().insert_one({
                "name": name, 
                "order": order,
                "branch_id": safe_object_id(branch_id) if branch_id else None
            })
            log_action("ADD_MENU", f"Added menu: {name}")
            trigger_notification("settings_update", "New Menu Created", f"A new sales menu '{name}' was added.", priority="INFO")
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
    menu = get_menus_collection().find_one({"_id": ObjectId(id)})
    if menu:
        get_menus_collection().delete_one({"_id": ObjectId(id)})
        log_action("DELETE_MENU", f"Deleted menu: {menu['name']}")
        trigger_notification("settings_update", "Sales Menu Removed", f"The sales menu '{menu['name']}' was deleted.", priority="WARNING")
        flash("Menu deleted.", "info")
    section = request.form.get('section', 'cats-menus')
    return redirect(url_for('auth.profile', tab='settings', section=section))

@admin_bp.route('/settings/menu/thresholds', methods=['POST'])
@login_required
@role_required('cashier')
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
    # Removed authorization code requirement as requested
    get_items_collection().delete_many({})
    get_purchase_collection().delete_many({})
    get_inventory_log_collection().delete_many({})
    get_system_log_collection().delete_many({})
    
    log_action("CLEAR_DATABASE", "Owner wiped all business records without code.")
    trigger_notification("data_purge", "SYSTEM DATA PURGE", "A complete database wipe was executed by the owner.", priority="CRITICAL")
    flash("All data has been cleared successfully!", "warning")
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
            "settings": list(get_settings_collection().find({}, {'_id': 0}))
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
            "notes": get_notes_collection()
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

@admin_bp.route('/settings/send-auth-code', methods=['POST'])
@login_required
@role_required('owner')
def send_auth_code():
    code = str(random.randint(100000, 999999))
    session['auth_code'] = code
    session['auth_code_expiry'] = (datetime.now() + timedelta(minutes=10)).isoformat()
    recipient = session.get("email")
    success = send_email_notification("Owner Security Authorization Code", f"SECURITY ALERT: Your Authorization Code is: {code}", override_recipient=recipient)
    return jsonify({"success": success, "message": f"Verification code sent to {recipient}" if success else "Failed to send email."})

@admin_bp.route('/settings/database-stats')
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

@admin_bp.route('/settings/test-email', methods=['POST'])
@login_required
@role_required('owner')
def test_email():
    import smtplib
    from email.mime.text import MIMEText
    from extensions import socketio
    from core.utils import safe_object_id, get_site_config
    
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

@admin_bp.route('/admin/settings/update', methods=['POST'])
@login_required
@role_required('owner')
def update_settings():
    section = request.form.get('section', 'general')
    upd = {}
    
    # Define which keys are expected as checkboxes for each section
    # This ensures that if they are missing from request.form (unchecked), they are set to False
    checkbox_map = {
        "notifications-config": [
            "email_notif_stock_in", "email_notif_stock_out", 
            "email_notif_low_stock", "email_notif_sales", 
            "email_notif_login", "email_notif_profile", 
            "email_notif_inventory", "email_notif_bulletin",
            "email_daily_summary", "email_weekly_summary", 
            "email_monthly_summary", "email_yearly_summary"
        ],
        "smtp-config": ["smtp_use_tls", "smtp_use_ssl"],
        "command-center": [
            "cc_show_progress", "cc_show_velocity", "cc_show_growth", "cc_show_dormant",
            "cc_show_txns", "cc_show_alerts", "cc_show_trending", 
            "cc_show_fleet_ranking", "cc_show_elite_cashiers"
        ],
        "biz-identity": ["maintenance_mode"]
    }

    # Handle explicit form fields
    for k in request.form:
        if k != 'section':
            v = request.form.get(k)
            # Standard checkbox 'on' handling
            if v == 'on':
                upd[k] = True
            else:
                upd[k] = v

    # Explicitly handle unchecked checkboxes for the current section
    if section in checkbox_map:
        for key in checkbox_map[section]:
            if key not in request.form:
                upd[key] = False

    # Push notification preferences are stored per-user, not globally
    if section == 'push-notif-prefs':
        def to_24h(hour, ampm):
            """Convert 12h hour + AM/PM to 24h integer."""
            h = int(hour)
            if ampm == 'PM' and h != 12:
                h += 12
            elif ampm == 'AM' and h == 12:
                h = 0
            return h

        prefs = {
            "daily_summary": request.form.get('pref_daily_summary') == 'on',
            "weekly_summary": request.form.get('pref_weekly_summary') == 'on',
            "monthly_summary": request.form.get('pref_monthly_summary') == 'on',
            "yearly_summary": request.form.get('pref_yearly_summary') == 'on',
            "low_stock_alerts": request.form.get('pref_low_stock_alerts') == 'on',
            "daily_hour": int(request.form.get('daily_hour', 11)),
            "daily_ampm": request.form.get('daily_ampm', 'PM'),
            "weekly_hour": int(request.form.get('weekly_hour', 11)),
            "weekly_ampm": request.form.get('weekly_ampm', 'PM'),
            "monthly_hour": int(request.form.get('monthly_hour', 11)),
            "monthly_ampm": request.form.get('monthly_ampm', 'PM'),
            "yearly_hour": int(request.form.get('yearly_hour', 11)),
            "yearly_ampm": request.form.get('yearly_ampm', 'PM'),
        }
        get_users_collection().update_one(
            {"email": session.get('email')},
            {"$set": {"notification_preferences": prefs}}
        )

        # Dynamically reschedule APScheduler jobs with the new times
        try:
            from app import scheduler
            from core.utils import safe_object_id, generate_sales_summary

            daily_24 = to_24h(prefs['daily_hour'], prefs['daily_ampm'])
            weekly_24 = to_24h(prefs['weekly_hour'], prefs['weekly_ampm'])
            monthly_24 = to_24h(prefs['monthly_hour'], prefs['monthly_ampm'])
            yearly_24 = to_24h(prefs['yearly_hour'], prefs['yearly_ampm'])

            for job_id, trigger_kwargs, label in [
                ('daily_summary', {'hour': daily_24, 'minute': 0}, 'Daily'),
                ('weekly_summary', {'day_of_week': 'sun', 'hour': weekly_24, 'minute': 0}, 'Weekly'),
                ('monthly_summary', {'day': 'last', 'hour': monthly_24, 'minute': 0}, 'Monthly'),
                ('yearly_summary', {'month': 12, 'day': 31, 'hour': yearly_24, 'minute': 0}, 'Yearly'),
            ]:
                try:
                    scheduler.reschedule_job(job_id, trigger='cron', **trigger_kwargs)
                except Exception:
                    scheduler.add_job(
                        lambda lbl=label: generate_sales_summary(lbl),
                        'cron', id=job_id, replace_existing=True, **trigger_kwargs
                    )
        except Exception as e:
            current_app.logger.warning(f"Could not reschedule jobs: {e}")

        log_action("UPDATE_NOTIF_PREFS", "User updated notification schedule preferences.")
        flash("Notification preferences saved!", "success")
        return redirect(url_for('auth.profile', tab='settings', section='notifications-config'))

    upd['updated_at'] = datetime.now(timezone.utc)
    settings_collection = get_settings_collection()
    settings_collection.update_one({"type": "general"}, {"$set": upd}, upsert=True)
    
    if section == 'notifications-config' or section == 'smtp-config':
        try:
            reschedule_periodic_jobs(current_app.scheduler)
        except Exception as e:
            current_app.logger.error(f"Scheduler Update Failed: {str(e)}")

    log_action("UPDATE_SETTINGS", f"Section: {section}")
    flash(f"Settings for {section} updated successfully.", "success")
    return redirect(url_for('auth.profile', tab='settings', section=section))
