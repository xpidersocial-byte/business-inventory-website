from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response, current_app
from core.utils import get_site_config, log_action, send_email_notification, MongoJSONProvider
from core.middleware import login_required, role_required, get_cashier_permissions
from core.db import get_users_collection, get_settings_collection, get_items_collection, get_categories_collection, get_menus_collection, get_purchase_collection, get_sales_collection, get_inventory_log_collection, get_system_log_collection, get_notes_collection
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import os
import json
import random
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/accounts')
@login_required
def admin_accounts():
    if session.get('role') != 'owner':
        flash("Access Denied.", "danger")
        return redirect(url_for('dashboard.dashboard'))
    
    users_collection = get_users_collection()
    all_users = list(users_collection.find({}, {'password': 0}))
    return render_template('admin_accounts.html', 
                           users=all_users, 
                           perms=get_cashier_permissions(),
                           role=session.get('role'))

@admin_bp.route('/admin/permissions/update', methods=['POST'])
@login_required
@role_required('owner')
def update_permissions():
    settings_collection = get_settings_collection()
    fields = [
        "dashboard", "items_master", "sales_ledger", "sales_summary", 
        "restock", "bulletin_board", "developer_portal", "live_debug", 
        "health_scanner", "admin_accounts", "general_setup", "system_logs",
        "setup_identity", "setup_localization", "setup_logic", "setup_users",
        "setup_categories", "setup_themes", "setup_advanced", "setup_assets", 
        "setup_backup", "setup_danger_zone", "setup_smtp", "setup_notifications"
    ]
    
    new_perms = {field: (request.form.get(field) == 'on') for field in fields}
    settings_collection.update_one({"type": "cashier_permissions"}, {"$set": new_perms}, upsert=True)
    
    log_action("UPDATE_PERMISSIONS", "Owner updated cashier access levels.")
    flash("Cashier permissions updated successfully!", "success")
    return redirect(url_for('admin.admin_accounts'))

@admin_bp.route('/general-setup')
@login_required
@role_required('owner')
def general_setup():
    users_collection = get_users_collection()
    menus_collection = get_menus_collection()
    categories_collection = get_categories_collection()
    
    tech_files = {}
    for filename in ['robots.txt', 'sitemap.xml', 'manifest.json']:
        path = os.path.join(current_app.root_path, 'static', filename)
        try:
            with open(path, 'r') as f:
                tech_files[filename.replace('.', '_')] = f.read()
        except:
            tech_files[filename.replace('.', '_')] = ""

    all_users = list(users_collection.find({}, {'password': 0}))
    menus = list(menus_collection.find().sort("name", 1))
    categories = list(categories_collection.find().sort("name", 1))

    return render_template('general_setup.html', menus=menus,
                           role=session.get('role'),
                           tech_files=tech_files,
                           users=all_users,
                           categories=categories)

@admin_bp.route('/settings/profile/update', methods=['POST'])
@login_required
@role_required('owner')
def update_profile():
    settings_collection = get_settings_collection()
    def clean_num(val, default=0, is_int=False):
        if not val or str(val).strip() == "": return default
        try:
            return int(val) if is_int else float(val)
        except:
            return default

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
        "smtp_host": request.form.get('smtp_host', ''),
        "smtp_port": clean_num(request.form.get('smtp_port'), 587, True),
        "smtp_user": request.form.get('smtp_user', ''),
        "smtp_password": request.form.get('smtp_password', ''),
        "smtp_sender": request.form.get('smtp_sender', ''),
        "smtp_use_tls": request.form.get('smtp_use_tls') == 'on',
        "smtp_use_ssl": request.form.get('smtp_use_ssl') == 'on',
        "email_notif_stock_in": request.form.get('email_notif_stock_in') == 'on',
        "email_notif_stock_out": request.form.get('email_notif_stock_out') == 'on',
        "email_notif_low_stock": request.form.get('email_notif_low_stock') == 'on',
        "email_notif_sales": request.form.get('email_notif_sales') == 'on',
        "email_recipient_list": request.form.get('email_recipient_list', ''),
        "updated_at": datetime.now()
    }
    
    settings_collection.update_one({"type": "general"}, {"$set": update_data}, upsert=True)
    log_action("UPDATE_PROFILE", f"Updated comprehensive site configuration.")
    flash("Business Profile updated successfully!", "success")
    return redirect(url_for('admin.general_setup'))

@admin_bp.route('/settings/login-bg/update', methods=['POST'])
@login_required
@role_required('owner')
def update_login_bg():
    settings_collection = get_settings_collection()
    if 'login_bg' not in request.files:
        flash("No file part", "danger")
        return redirect(url_for('admin.admin_accounts'))
    
    file = request.files['login_bg']
    if file.filename == '':
        flash("No selected file", "danger")
        return redirect(url_for('admin.admin_accounts'))
    
    if file:
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        new_filename = f"login_bg_{int(datetime.now().timestamp())}.{ext}"
        target_path = os.path.join(current_app.root_path, 'static', 'images', new_filename)
        file.save(target_path)
        
        settings_collection.update_one(
            {"type": "general"},
            {"$set": {"login_background": f"images/{new_filename}"}}
        )
        
        log_action("UPDATE_LOGIN_BG", "Updated login page background image.")
        flash("Login background updated!", "success")
    return redirect(url_for('admin.admin_accounts'))

@admin_bp.route('/settings/favicon/update', methods=['POST'])
@login_required
@role_required('owner')
def update_favicon():
    if 'favicon' not in request.files:
        flash("No file part", "danger")
        return redirect(url_for('admin.admin_accounts'))
    
    file = request.files['favicon']
    if file.filename == '':
        flash("No selected file", "danger")
        return redirect(url_for('admin.admin_accounts'))
    
    if file:
        target_path = os.path.join(current_app.root_path, 'static', 'favicon.ico')
        file.save(target_path)
        log_action("UPDATE_FAVICON", "Updated website favicon.")
        flash("Favicon updated successfully!", "success")
    return redirect(url_for('admin.admin_accounts'))

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
        return Response(
            json.dumps(data, indent=4, cls=MongoJSONProvider),
            mimetype='application/json',
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        flash(f"Backup failed: {str(e)}", "danger")
        return redirect(url_for('admin.admin_accounts'))

@admin_bp.route('/settings/backup/restore', methods=['POST'])
@login_required
@role_required('owner')
def restore_backup():
    if 'backup_file' not in request.files:
        flash("No file uploaded", "danger")
        return redirect(url_for('admin.admin_accounts'))
    
    file = request.files['backup_file']
    if file.filename == '':
        flash("No file selected", "danger")
        return redirect(url_for('admin.admin_accounts'))

    try:
        data = json.load(file)
        mapping = {
            "items": get_items_collection(),
            "categories": get_categories_collection(),
            "purchase": get_purchase_collection(),
            "sales": get_sales_collection(),
            "inventory_log": get_inventory_log_collection(),
            "system_logs": get_system_log_collection(),
            "notes": get_notes_collection(),
            "users": get_users_collection(),
            "settings": get_settings_collection()
        }

        if not any(k in data for k in mapping.keys()):
            flash("Invalid backup format.", "danger")
            return redirect(url_for('admin.admin_accounts'))

        for key, collection in mapping.items():
            if key in data and isinstance(data[key], list):
                collection.delete_many({})
                if data[key]:
                    collection.insert_many(data[key])
        
        log_action("RESTORE_BACKUP", "Owner restored the system from a backup file.")
        flash("System restored successfully!", "success")
    except Exception as e:
        flash(f"Restore failed: {str(e)}", "danger")
    return redirect(url_for('admin.admin_accounts'))

@admin_bp.route('/settings/backup/restore/csv', methods=['POST'])
@login_required
@role_required('owner')
def restore_csv():
    if 'csv_file' not in request.files:
        flash("No file uploaded", "danger")
        return redirect(url_for('admin.admin_accounts'))
    
    file = request.files['csv_file']
    target = request.form.get('target_collection')
    
    if file.filename == '' or not target:
        flash("File or target collection missing", "danger")
        return redirect(url_for('admin.admin_accounts'))

    try:
        import csv
        from io import StringIO
        stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        data_to_insert = []
        
        def clean_val(val, type_func=float):
            if not val: return 0.0 if type_func == float else 0
            clean = val.replace("₱", "").replace(",", "").replace("%", "").strip()
            if clean.lower() == "low stock": return 0
            try:
                return type_func(clean)
            except:
                return 0.0 if type_func == float else 0

        for row in csv_input:
            mapped_row = {}
            if target == 'items':
                mapped_row['name'] = row.get('Item Name', row.get('name', 'Unknown Item'))
                mapped_row['category'] = row.get('Category', row.get('category', 'Uncategorized'))
                mapped_row['cost_price'] = clean_val(row.get('Cost Price', row.get('cost_price', '0')))
                mapped_row['retail_price'] = clean_val(row.get('Retail Price', row.get('retail_price', '0')))
                mapped_row['stock'] = int(clean_val(row.get('Quantity Available', row.get('stock', '0')), int))
                mapped_row['sold'] = int(clean_val(row.get('Quantity Sale', row.get('sold', '0')), int))
                if not mapped_row['name'] or mapped_row['name'].strip() == "":
                    continue
                data_to_insert.append(mapped_row)
            elif target == 'categories':
                name = row.get('Category', row.get('name'))
                if name and name.strip() != "":
                    data_to_insert.append({"name": name.strip()})
        
        if target == 'items':
            if data_to_insert:
                get_items_collection().delete_many({})
                get_items_collection().insert_many(data_to_insert)
                unique_cats = sorted(list(set([item['category'] for item in data_to_insert if item.get('category')])))
                if unique_cats:
                    get_categories_collection().delete_many({})
                    get_categories_collection().insert_many([{"name": cat} for cat in unique_cats])
            else:
                flash("No valid data found in CSV for Items.", "warning")
                return redirect(url_for('admin.admin_accounts'))
        elif target == 'categories':
            if data_to_insert:
                unique_cats = {c['name']: c for c in data_to_insert}.values()
                get_categories_collection().delete_many({})
                get_categories_collection().insert_many(list(unique_cats))
            else:
                flash("No valid data found in CSV for Categories.", "warning")
                return redirect(url_for('admin.admin_accounts'))
            
        log_action("RESTORE_CSV", f"Owner restored {target} collection from CSV.")
        flash(f"{target.capitalize()} restored successfully from CSV!", "success")
    except Exception as e:
        flash(f"CSV Restore failed: {str(e)}", "danger")
    return redirect(url_for('admin.admin_accounts'))

@admin_bp.route('/settings/category/add', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('name')
    if name:
        if get_categories_collection().find_one({"name": name}):
            flash("Category already exists!", "danger")
        else:
            get_categories_collection().insert_one({"name": name})
            log_action("ADD_CATEGORY", f"Added category: {name}")
            flash(f"Category '{name}' added!", "success")
    return redirect(url_for('admin.admin_accounts'))

@admin_bp.route('/settings/category/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_category(id):
    cat = get_categories_collection().find_one({"_id": ObjectId(id)})
    if cat:
        get_categories_collection().delete_one({"_id": ObjectId(id)})
        log_action("DELETE_CATEGORY", f"Deleted category: {cat['name']}")
        flash("Category deleted.", "info")
    return redirect(url_for('admin.admin_accounts'))

@admin_bp.route('/settings/user/add', methods=['POST'])
@login_required
@role_required('owner')
def add_user():
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role', 'cashier')
    if email and password:
        if get_users_collection().find_one({"email": email}):
            flash("User already exists!", "danger")
        else:
            get_users_collection().insert_one({"email": email, "password": password, "role": role})
            log_action("ADD_USER", f"Created user: {email} ({role})")
            flash(f"User '{email}' created successfully!", "success")
    return redirect(url_for('admin.admin_accounts'))

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
            flash("User deleted.", "info")
    return redirect(url_for('admin.admin_accounts'))

@admin_bp.route('/settings/user/edit/<id>', methods=['POST'])
@login_required
@role_required('owner')
def edit_user(id):
    user = get_users_collection().find_one({"_id": ObjectId(id)})
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('admin.admin_accounts'))

    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')
    verification_code = request.form.get('verification_code')

    is_protected = user.get('role') == 'owner' or user.get('email') == 'admin@inventory.com'
    if is_protected or role == 'owner':
        stored_code = session.get('auth_code')
        expiry_str = session.get('auth_code_expiry')
        if not stored_code or not expiry_str:
            flash("Authorization required. Please send a code to your email first.", "danger")
            return redirect(url_for('admin.admin_accounts'))
        expiry = datetime.fromisoformat(expiry_str)
        if datetime.now() > expiry:
            flash("Security code has expired. Please request a new one.", "danger")
            return redirect(url_for('admin.admin_accounts'))
        if verification_code != stored_code:
            flash("Invalid Security Code! Authorization denied.", "danger")
            return redirect(url_for('admin.admin_accounts'))
        session.pop('auth_code', None)
        session.pop('auth_code_expiry', None)

    update_data = {}
    if email: update_data['email'] = email
    if password: update_data['password'] = password
    if role: update_data['role'] = role

    if update_data:
        get_users_collection().update_one({"_id": ObjectId(id)}, {"$set": update_data})
        log_action("EDIT_USER", f"Updated account credentials for: {user['email']}")
        flash(f"Account for {user['email']} updated successfully!", "success")
    return redirect(url_for('admin.admin_accounts'))

@admin_bp.route('/settings/menu/add', methods=['POST'])
@login_required
@role_required('owner')
def add_menu():
    name = request.form.get('name')
    icon = request.form.get('icon', 'bi-list-stars')
    warning = request.form.get('warning_threshold', 10)
    low = request.form.get('low_stock_threshold', 5)
    if name:
        if get_menus_collection().find_one({"name": name}):
            flash("Menu anchor already exists!", "danger")
        else:
            get_menus_collection().insert_one({
                "name": name,
                "icon": icon,
                "warning_threshold": int(warning),
                "low_stock_threshold": int(low)
            })
            log_action("ADD_MENU", f"Added menu anchor: {name}")
            flash(f"Menu '{name}' created!", "success")
    return redirect(url_for('admin.general_setup'))

@admin_bp.route('/settings/menu/update/<id>', methods=['POST'])
@login_required
@role_required('owner')
def update_menu(id):
    warning = request.form.get('warning_threshold', 10)
    low = request.form.get('low_stock_threshold', 5)
    icon = request.form.get('icon', 'bi-list-stars')
    get_menus_collection().update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "warning_threshold": int(warning),
            "low_stock_threshold": int(low),
            "icon": icon
        }}
    )
    flash("Menu thresholds updated!", "success")
    return redirect(url_for('admin.general_setup'))

@admin_bp.route('/settings/global-thresholds/update', methods=['POST'])
@login_required
def update_global_thresholds_ajax():
    data = request.get_json()
    warning = data.get('warning', 10)
    low = data.get('low', 5)
    
    get_settings_collection().update_one(
        {"type": "general"},
        {"$set": {
            "warning_threshold": int(warning),
            "low_stock_threshold": int(low)
        }},
        upsert=True
    )
    return jsonify({"success": True})

@admin_bp.route('/settings/menu/update-ajax', methods=['POST'])
@login_required
def update_menu_ajax():
    data = request.get_json()
    menu_id = data.get('id')
    warning = data.get('warning')
    low = data.get('low')
    if menu_id:
        get_menus_collection().update_one(
            {"_id": ObjectId(menu_id)},
            {"$set": {
                "warning_threshold": int(warning),
                "low_stock_threshold": int(low)
            }}
        )
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Invalid menu ID"}), 400

@admin_bp.route('/settings/menu/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_menu(id):
    menu = get_menus_collection().find_one({"_id": ObjectId(id)})
    if menu:
        get_menus_collection().delete_one({"_id": ObjectId(id)})
        log_action("DELETE_MENU", f"Deleted menu: {menu['name']}")
        flash("Menu anchor deleted.", "info")
    return redirect(url_for('admin.general_setup'))

@admin_bp.route('/admin/send-auth-code', methods=['POST'])
@login_required
@role_required('owner')
def send_auth_code():
    code = str(random.randint(100000, 999999))
    session['auth_code'] = code
    session['auth_code_expiry'] = (datetime.now() + timedelta(minutes=10)).isoformat()
    recipient = "bejasadhev@gmail.com"
    subject = "Owner Security Authorization Code"
    body = f"SECURITY ALERT: Your Authorization Code is: {code}"
    success = send_email_notification(subject, body, override_recipient=recipient)
    if success:
        return jsonify({"success": True, "message": f"Verification code sent to {recipient}"})
    else:
        return jsonify({"success": False, "message": "Failed to send email."})

@admin_bp.route('/settings/api/update', methods=['POST'])
@login_required
@role_required('owner')
def update_api_key():
    import ai_engine
    import importlib
    api_key = request.form.get('api_key')
    api_type = request.form.get('api_type', 'openrouter')
    if api_key:
        env_path = os.path.join(current_app.root_path, '.env')
        env_var = "GEMINI_API_KEY" if api_type == 'gemini' else "OPENROUTER_API_KEY"
        lines = []
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = [line for line in f.readlines() if not line.startswith(f'{env_var}=')]
        lines = [l for l in lines if l.strip()]
        with open(env_path, 'w') as f:
            for line in lines:
                f.write(line.strip() + '\n')
            f.write(f'{env_var}={api_key.strip()}\n')
        load_dotenv(override=True)
        importlib.reload(ai_engine)
        log_action("UPDATE_API_KEY", f"Updated {api_type.capitalize()} API Key.")
        flash(f"{api_type.capitalize()} API Key updated successfully!", "success")
    return redirect(url_for('admin.admin_accounts'))

@admin_bp.route('/system-logs')
@login_required
@role_required('owner')
def system_logs():
    logs = list(get_system_log_collection().find().sort("timestamp", -1).limit(100))
    return render_template('system_logs.html', logs=logs, role=session.get('role'))

@admin_bp.route('/settings/data/clear', methods=['POST'])
@login_required
@role_required('owner')
def clear_all_data():
    verification_code = request.form.get('verification_code')
    stored_code = session.get('auth_code')
    expiry_str = session.get('auth_code_expiry')
    
    if not stored_code or not expiry_str:
        flash("Authorization required. Please send a code to your email first.", "danger")
        return redirect(url_for('admin.general_setup'))
        
    expiry = datetime.fromisoformat(expiry_str)
    if datetime.now() > expiry:
        flash("Security code has expired. Please request a new one.", "danger")
        return redirect(url_for('admin.general_setup'))
        
    if verification_code != stored_code:
        flash("Invalid Security Code! Data wipe denied.", "danger")
        return redirect(url_for('admin.general_setup'))

    session.pop('auth_code', None)
    session.pop('auth_code_expiry', None)

    get_items_collection().delete_many({})
    get_purchase_collection().delete_many({})
    get_inventory_log_collection().delete_many({})
    get_system_log_collection().delete_many({})
    
    log_action("CLEAR_DATABASE", "Owner wiped all business records.")
    flash("All business data has been cleared successfully!", "warning")
    return redirect(url_for('admin.general_setup'))
