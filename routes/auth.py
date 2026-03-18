from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, g
from core.utils import get_site_config, log_action
from core.middleware import login_required
from core.db import get_users_collection, get_subscriptions_collection
from datetime import datetime
from extensions import socketio

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    if 'email' in session:
        return redirect(url_for('dashboard.dashboard'))
    return render_template('login.html', site_config=get_site_config())

@auth_bp.route('/login', methods=['POST'])
def login():
    users_collection = get_users_collection()
    email = request.form.get('email')
    password = request.form.get('password')
    user = users_collection.find_one({"email": email, "password": password})
    if user:
        session['email'] = email
        session['role'] = user.get('role', 'cashier')
        session['theme'] = user.get('theme', 'default')
        log_action("LOGIN", f"User '{email}' logged in.")
        return redirect(url_for('dashboard.dashboard'))
    else:
        log_action("LOGIN_FAILED", f"Failed login attempt for email: {email}")
        flash("Invalid email or password!", "danger")
        return redirect(url_for('auth.index'))

@auth_bp.route('/logout')
def logout():
    log_action("LOGOUT", f"User '{session.get('email')}' logged out.")
    session.clear()
    return redirect(url_for('auth.index'))

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
