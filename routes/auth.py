from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, g, current_app
from core.utils import get_site_config, log_action, send_email_notification, trigger_notification, verify_password, hash_password
from core.middleware import login_required, get_cashier_permissions, get_owner_permissions
from core.db import get_users_collection, get_subscriptions_collection, get_system_log_collection, get_menus_collection, get_categories_collection, get_branches_collection
from datetime import datetime, timedelta
from extensions import socketio
import os
from werkzeug.utils import secure_filename

auth_bp = Blueprint('auth', __name__)

def get_status_string(last_active):
    if not last_active:
        return "Offline"
    
    now = datetime.now()
    diff = now - last_active
    
    if diff < timedelta(minutes=5):
        return "Online"
    elif diff < timedelta(minutes=15):
        return "Away"
    
    minutes = int(diff.total_seconds() / 60)
    if minutes < 60:
        return f"Active {minutes}m ago"
    
    hours = int(minutes / 60)
    if hours < 24:
        return f"Active {hours}h ago"
    
    return f"Active {int(hours/24)}d ago"

@auth_bp.route('/')
def index():
    if 'email' in session:
        return redirect(url_for('branches.select_branch'))
    return redirect(url_for('auth.login_page'))

@auth_bp.route('/login', methods=['GET'])
def login_page():
    if 'email' in session:
        return redirect(url_for('branches.select_branch'))
    return render_template('login.html', site_config=get_site_config())

@auth_bp.route('/login', methods=['POST'])
def login():
    users_collection = get_users_collection()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    user = users_collection.find_one({"email": email})
    if user and verify_password(user.get('password'), password):
        session['email'] = email
        session['role'] = user.get('role', 'cashier')
        session['theme'] = user.get('theme', 'default')
        # Logic update: Cashiers are now forced to pass through the select-branch page
        # even if they have an assigned branch in their account.
        # session['branch_id'] = user.get('branch_id')
        users_collection.update_one({"email": email}, {"$set": {"last_ip": request.remote_addr}})
        log_action("LOGIN", f"User '{email}' logged in.")
        send_email_notification(
            "User Login",
            f"User '{email}' successfully logged in at {datetime.now().strftime('%Y-%m-%d %I:%M %p')}.",
            notif_type="login"
        )
        return redirect(url_for('branches.select_branch'))
    else:
        log_action("LOGIN_FAILED", f"Failed login attempt for email: {email}")
        send_email_notification(
            "⚠️ Failed Login Attempt",
            f"A failed login attempt was made for the account: {email}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}\nIP: {request.remote_addr}\n\nIf this was not you, your system may be under attack.",
            notif_type="login"
        )
        flash("Invalid email or password!", "danger")
        return redirect(url_for('auth.login_page'))

@auth_bp.route('/logout')
def logout():
    log_action("LOGOUT", f"User '{session.get('email')}' logged out.")
    session.clear()
    return redirect(url_for('auth.login_page'))

@auth_bp.route('/update-theme', methods=['POST'])
@login_required
def update_theme():
    users_collection = get_users_collection()
    theme = request.json.get('theme', 'default')
    email = session.get('email')
    
    users_collection.update_one(
        {"email": email},
        {"$set": {"theme": theme}}
    )
    session['theme'] = theme
    socketio.emit('theme_update', {'theme': theme})
    return jsonify({"success": True, "theme": theme})

@auth_bp.route('/profile')
@login_required
def profile():
    users_collection = get_users_collection()
    system_log_collection = get_system_log_collection()
    email = session['email']
    user = users_collection.find_one({"email": email})
    
    if not user:
        # User in session but not in DB (common after DB migration/clear)
        session.clear()
        flash("Your session has expired or your account was not found in the new database.", "warning")
        return redirect(url_for('auth.index'))
    
    # Process current user status
    user['status_text'] = get_status_string(user.get('last_active'))
    
    # Get personal activity logs
    logs = list(system_log_collection.find({"email": email}).sort("timestamp", -1).limit(20))
    
    # Mark admin settings as read if viewing settings tab
    tab = request.args.get('tab')
    if tab == 'settings':
        try:
            from core.db import get_notifications_collection
            branch_id = session.get('branch_id')
            admin_notif_q = {"type": {"$in": ["user_added", "user_updated", "user_deleted", "perms_update", "settings_update", "backup_import", "data_purge"]}, "read_by": {"$ne": email}}
            if branch_id:
                admin_notif_q["branch_id"] = branch_id
                
            get_notifications_collection().update_many(
                admin_notif_q,
                {"$addToSet": {"read_by": email}}
            )
            socketio.emit('dashboard_update')
        except: pass

    # Get all users for messaging directory
    raw_users = list(users_collection.find({}, {"email": 1, "role": 1, "branch_id": 1, "profile_pic": 1, "first_name": 1, "last_name": 1, "last_active": 1, "last_ip": 1}))
    all_users = []
    for u in raw_users:
        u['status_text'] = get_status_string(u.get('last_active'))
        all_users.append(u)
    
    # SECTION: Admin/Owner Specific Data
    admin_data = {}
    if session.get('role') == 'owner':
        menus_collection = get_menus_collection()
        categories_collection = get_categories_collection()
        
        # Fetch all system logs for Admin Activity section
        all_logs = list(system_log_collection.find().sort("timestamp", -1).limit(200))
        
        tech_files = {}
        for filename in ['robots.txt', 'sitemap.xml', 'manifest.json']:
            path = os.path.join(current_app.root_path, 'static', filename)
            try:
                with open(path, 'r') as f:
                    tech_files[filename.replace('.', '_')] = f.read()
            except:
                tech_files[filename.replace('.', '_')] = ""

        # FETCH CATEGORIES AND MENUS
        branch_id = session.get('branch_id')
        cat_query = {"branch_id": branch_id} if branch_id else {}
        menu_query = {"branch_id": branch_id} if branch_id else {}
        
        db_cats = list(categories_collection.find(cat_query).sort("name", 1))
        db_menus = list(menus_collection.find(menu_query).sort("order", 1))

        current_app.logger.info(f"Populating admin_data for OWNER. Cats: {len(db_cats)}, Menus: {len(db_menus)}")

        db_branches = []
        for b in get_branches_collection().find().sort("name", 1):
            b['_id'] = str(b['_id'])
            db_branches.append(b)

        admin_data = {
            "all_users": all_users,
            "all_logs": all_logs,
            "menus": db_menus,
            "categories": db_cats,
            "branches": db_branches,
            "tech_files": tech_files,
            "cashier_perms": get_cashier_permissions(),
            "owner_perms": get_owner_permissions()
        }
    
    return render_template('profile.html', 
                           user=user, 
                           logs=logs, 
                           all_users=all_users, 
                           admin_data=admin_data)

@auth_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    users_collection = get_users_collection()
    email = session.get('email')
    user = users_collection.find_one({"email": email})
    new_email = request.form.get('email').strip().lower() if request.form.get('email') else None
    new_password = request.form.get('password')
    confirm_code = request.form.get('confirm_code', '').strip()
    
    # Require confirmation code for any change
    stored_code = session.get('profile_confirm_code')
    expiry_str = session.get('profile_confirm_expiry')
    if not stored_code or not expiry_str:
        flash("Please request a confirmation code before updating your profile.", "warning")
        return redirect(url_for('auth.profile'))
    if datetime.now() > datetime.fromisoformat(expiry_str):
        session.pop('profile_confirm_code', None)
        session.pop('profile_confirm_expiry', None)
        flash("Confirmation code expired. Please request a new one.", "danger")
        return redirect(url_for('auth.profile'))
    if confirm_code != stored_code:
        flash("Invalid confirmation code. Update cancelled.", "danger")
        return redirect(url_for('auth.profile'))
    
    # Code is valid — consume it
    session.pop('profile_confirm_code', None)
    session.pop('profile_confirm_expiry', None)
    
    update_data = {
        "first_name": request.form.get('first_name', ''),
        "last_name": request.form.get('last_name', ''),
        "phone": request.form.get('phone', ''),
        "job_title": request.form.get('job_title', ''),
        "department": request.form.get('department', ''),
        "location": request.form.get('location', ''),
        "bio": request.form.get('bio', '')
    }
    
    # Handle user-specific notification preferences if in the personal settings tab
    if request.form.get('tab', 'about') == 'about':
        update_data["notification_preferences"] = {
            "daily_summary": request.form.get('pref_daily_summary') == 'on',
            "weekly_summary": request.form.get('pref_weekly_summary') == 'on',
            "monthly_summary": request.form.get('pref_monthly_summary') == 'on',
            "yearly_summary": request.form.get('pref_yearly_summary') == 'on'
        }
    
    if new_email and new_email != email:
        if users_collection.find_one({"email": new_email}):
            flash("Email already in use!", "danger")
            return redirect(url_for('auth.profile'))
        update_data['email'] = new_email
        
    if new_password:
        update_data['password'] = hash_password(new_password)
        
    users_collection.update_one({"email": email}, {"$set": update_data})
    
    if 'email' in update_data:
        session['email'] = update_data['email']
        
    log_action("PROFILE_UPDATE", f"User '{email}' updated their profile.")
    trigger_notification("user_updated", "Profile Updated", f"User '{email}' updated their profile information.", priority="SUCCESS")
    
    send_email_notification(
        "Profile Updated",
        f"The profile for '{email}' was successfully updated at {datetime.now().strftime('%Y-%m-%d %I:%M %p')}.\n\nIf you did not make this change, please contact your administrator immediately.",
        notif_type="profile"
    )
    tab = request.form.get('tab', 'about')
    section = request.form.get('section')
    flash("Profile information updated successfully!", "success")
    return redirect(url_for('auth.profile', tab=tab, section=section))

@auth_bp.route('/profile/upload-photo', methods=['POST'])
@login_required
def upload_photo():
    if 'photo' not in request.files:
        return jsonify({"success": False, "message": "No file part"}), 400
    
    file = request.files['photo']
    if file.filename == '':
        return jsonify({"success": False, "message": "No selected file"}), 400
    
    if file:
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        new_filename = f"profile_{session['email'].split('@')[0]}_{int(datetime.now().timestamp())}.{ext}"
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
        os.makedirs(upload_folder, exist_ok=True)
        
        file.save(os.path.join(upload_folder, new_filename))
        photo_path = f"uploads/profiles/{new_filename}"
        
        get_users_collection().update_one(
            {"email": session['email']},
            {"$set": {"profile_pic": photo_path}}
        )
        
        log_action("UPDATE_PROFILE_PIC", "Updated profile picture.")
        trigger_notification("user_updated", "Avatar Updated", f"{session['email']} updated their profile picture.", priority="INFO")
        return jsonify({"success": True, "path": photo_path})

@auth_bp.route('/profile/upload-cover', methods=['POST'])
@login_required
def upload_cover():
    if 'photo' not in request.files:
        return jsonify({"success": False, "message": "No file part"}), 400
    
    file = request.files['photo']
    if file:
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        new_filename = f"cover_{session['email'].split('@')[0]}_{int(datetime.now().timestamp())}.{ext}"
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'covers')
        os.makedirs(upload_folder, exist_ok=True)
        
        file.save(os.path.join(upload_folder, new_filename))
        cover_path = f"uploads/covers/{new_filename}"
        
        get_users_collection().update_one(
            {"email": session['email']},
            {"$set": {"cover_photo": cover_path}}
        )
        
        log_action("UPDATE_COVER_PHOTO", "Updated cover photo.")
        trigger_notification("user_updated", "Cover Updated", f"{session['email']} updated their cover photo.", priority="INFO")
        return jsonify({"success": True, "path": cover_path})

@auth_bp.route('/forgot-password')
def forgot_password():
    return render_template('forgot_password.html', site_config=get_site_config())

@auth_bp.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    subscriptions_collection = get_subscriptions_collection()
    subscription_json = request.get_json()
    if not subscription_json:
        return jsonify({"success": False, "message": "Invalid subscription"}), 400
    
    subscriptions_collection.update_one(
        {"subscription_json.endpoint": subscription_json['endpoint']},
        {"$set": {"subscription_json": subscription_json, "email": session.get('email'), "updated_at": datetime.now()}},
        upsert=True
    )
    return jsonify({"success": True, "message": "Subscribed to push notifications!"})

@auth_bp.route('/auth/send-profile-code', methods=['POST'])
@login_required
def send_profile_confirm_code():
    import random
    
    email = session.get('email')
    role = session.get('role', 'cashier')
    user = get_users_collection().find_one({"email": email})
    
    # Codes are sent to the registered email of the account being modified
    recipient = user.get('email', email) if user else email
    
    code = str(random.randint(100000, 999999))
    session['profile_confirm_code'] = code
    session['profile_confirm_expiry'] = (datetime.now() + timedelta(minutes=10)).isoformat()
    
    success = send_email_notification(
        "Profile Update Confirmation Code",
        f"Your profile update confirmation code is: {code}\n\nThis code expires in 10 minutes.\nIf you did not request this, please ignore this email.",
        override_recipient=recipient
    )
    if success:
        return jsonify({"success": True, "message": f"Confirmation code sent to {recipient}"})
    else:
        return jsonify({"success": False, "message": "Failed to send email. Please check your SMTP settings."})

@auth_bp.route('/forgot-password/request', methods=['POST'])
def forgot_password_request():
    import random
    email = request.form.get('email', '').strip().lower()
    if not email:
        return jsonify({"success": False, "message": "Email is required."}), 400
    
    users_collection = get_users_collection()
    user = users_collection.find_one({"email": email})
    if user:
        code = str(random.randint(100000, 999999))
        expiry = datetime.now() + timedelta(minutes=15)
        
        users_collection.update_one(
            {"email": email},
            {"$set": {"reset_code": code, "reset_code_expiry": expiry}}
        )
        
        success = send_email_notification(
            "Password Reset Code",
            f"Your password reset code is: {code}\n\nThis code expires in 15 minutes.\nIf you did not request this, please ignore this email.",
            override_recipient=email
        )
        if not success:
            return jsonify({"success": False, "message": "Failed to send reset code. Please try again later or contact support."}), 500
            
    return jsonify({"success": True, "message": "A reset code has been sent to your email address."})

@auth_bp.route('/forgot-password/reset', methods=['POST'])
def forgot_password_reset():
    email = request.form.get('email', '').strip().lower()
    code = request.form.get('code', '').strip()
    new_password = request.form.get('password', '')
    
    if not email or not code or not new_password:
        return jsonify({"success": False, "message": "All fields are required."}), 400
        
    users_collection = get_users_collection()
    user = users_collection.find_one({"email": email})
    
    if not user:
        return jsonify({"success": False, "message": "Invalid email or code."}), 400
        
    stored_code = user.get('reset_code')
    expiry = user.get('reset_code_expiry')
    
    if not stored_code or not expiry or datetime.now() > expiry or stored_code != code:
        return jsonify({"success": False, "message": "Invalid or expired reset code."}), 400
        
    users_collection.update_one(
        {"email": email},
        {
            "$set": {"password": hash_password(new_password)},
            "$unset": {"reset_code": "", "reset_code_expiry": ""}
        }
    )
    
    log_action("PASSWORD_RESET", f"Password set dynamically for {email}.")
    return jsonify({"success": True, "message": "Password successfully reset! You can now log in."})
