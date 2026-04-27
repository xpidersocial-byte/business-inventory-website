import random
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from core.middleware import login_required, role_required
from core.db import get_branches_collection, get_inventory_log_collection, get_items_collection, get_purchase_collection, get_users_collection
from core.utils import log_action, trigger_notification, get_site_config, calculate_item_metrics, send_email_notification
from bson.objectid import ObjectId
from datetime import datetime, timezone, timedelta

branches_bp = Blueprint('branches', __name__)

@branches_bp.route('/branches')
@login_required
@role_required('owner')
def branch_list():
    branches_col = get_branches_collection()
    branches = list(branches_col.find().sort("name", 1))
    # --- Performance Aggregation ---
    items_col = get_items_collection()
    purchase_col = get_purchase_collection()
    users_col = get_users_collection()
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    
    from core.db import get_menus_collection
    global_low = get_site_config().get('low_stock_threshold', 5)
    menus_map = {m['name']: m.get('low_stock_threshold', global_low) for m in get_menus_collection().find()}
    
    for branch in branches:
        b_id = str(branch["_id"])
        # Stock Stats
        q = {"branch_id": {"$in": [b_id, ObjectId(b_id)]}, "active": {"$ne": False}}
        branch_items = list(items_col.find(q))
        low_stock = 0
        for item in branch_items:
            try:
                stock = float(item.get('stock', 0))
                low_threshold = item.get('low_threshold')
                if low_threshold is None:
                    menu_name = item.get('menu')
                    if menu_name and menu_name in menus_map:
                        low_threshold = menus_map[menu_name]
                    else:
                        low_threshold = global_low
                
                if stock <= float(low_threshold): low_stock += 1
            except: continue
        branch["low_stock"] = low_stock
        branch["total_items"] = len(branch_items)
        
        # Sales Stats (Last 7 Days)
        revenue = 0
        for sale in purchase_col.find({"branch_id": b_id, "status": "Sold"}):
            try:
                ts = sale.get("timestamp") or sale.get("date")
                dt = ts if isinstance(ts, datetime) else datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
                if dt >= week_ago: revenue += float(sale.get("total", 0))
            except: continue
        branch["weekly_revenue"] = revenue
        
        # Staff Count
        branch["staff_count"] = users_col.count_documents({"branch_id": b_id})
    return render_template('branches.html', branches=branches, site_config=get_site_config())

@branches_bp.route('/branches/add', methods=['POST'])
@login_required
@role_required('owner')
def add_branch():
    name = request.form.get('name')
    location = request.form.get('location')
    contact = request.form.get('contact')
    
    if name:
        branches_col = get_branches_collection()
        branch_id = branches_col.insert_one({
            "name": name,
            "location": location,
            "contact": contact,
            "created_at": datetime.now(timezone.utc),
            "active": True
        }).inserted_id
        
        log_action("ADD_BRANCH", f"Created branch: {name}")
        trigger_notification("settings_update", "New Branch Created", f"Branch '{name}' has been added to the organization.", priority="SUCCESS")
        flash(f"Branch '{name}' created successfully!", "success")
    
    return redirect(url_for('branches.branch_list'))

@branches_bp.route('/branches/edit/<id>', methods=['POST'])
@login_required
@role_required('owner')
def edit_branch(id):
    name = request.form.get('name')
    location = request.form.get('location')
    contact = request.form.get('contact')
    
    if name:
        branches_col = get_branches_collection()
        branches_col.update_one({"_id": ObjectId(id)}, {"$set": {
            "name": name,
            "location": location,
            "contact": contact,
            "updated_at": datetime.now(timezone.utc)
        }})
        
        log_action("EDIT_BRANCH", f"Updated branch: {name}")
        flash(f"Branch '{name}' updated successfully!", "info")
    
    return redirect(url_for('branches.branch_list'))

@branches_bp.route('/branches/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_branch(id):
    verification_code = request.form.get('verification_code')
    stored_code = session.get('branch_delete_code')
    expiry_str = session.get('branch_delete_code_expiry')
    
    if not stored_code or not expiry_str or datetime.now(timezone.utc) > datetime.fromisoformat(expiry_str) or str(verification_code).strip() != stored_code:
        flash("Security authorization failed or expired. Please request a new code.", "danger")
        return redirect(url_for('branches.branch_list'))
    
    # Clear the code after successful validation
    session.pop('branch_delete_code', None)
    session.pop('branch_delete_code_expiry', None)

    branches_col = get_branches_collection()
    branch = branches_col.find_one({"_id": ObjectId(id)})
    
    if branch:
        branches_col.delete_one({"_id": ObjectId(id)})
        log_action("DELETE_BRANCH", f"Deleted branch: {branch['name']}")
        trigger_notification("settings_update", "Branch Removed", f"Branch '{branch['name']}' was deleted.", priority="WARNING")
        flash(f"Branch '{branch['name']}' deleted.", "warning")
        
    return redirect(url_for('branches.branch_list'))

    # Deprecated: The select_branch page has been removed in favor of the Nexus Sidebar Dropdown.
    return redirect(url_for('dashboard.dashboard'))

@branches_bp.route('/set-branch', methods=['POST'])
@login_required
def set_branch():
    branch_id = request.form.get('branch_id')
    role = session.get('role', 'cashier')
    
    if branch_id:
        session['branch_id'] = branch_id
        log_action("SWITCH_BRANCH", f"Switched to terminal: {branch_id}")
    else:
        if role == 'owner': # NULL means Global Fleet
            session['branch_id'] = None
            log_action("SWITCH_BRANCH", "Switched to Global Fleet Telemetry")
            
    return redirect(url_for('dashboard.dashboard'))

@branches_bp.route('/branches/request-delete-code', methods=['POST'])
@login_required
@role_required('owner')
def request_delete_code():
    code = str(random.randint(100000, 999999))
    session['branch_delete_code'] = code
    session['branch_delete_code_expiry'] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    
    recipient = session.get('email')
    success = send_email_notification(
        "Branch Deletion Security Code", 
        f"SECURITY ALERT: A request to delete a branch was initiated. Your verification code is: {code}\n\nThis code will expire in 10 minutes.",
        override_recipient=recipient
    )
    
    if success:
        return jsonify({"success": True, "message": f"Verification code sent to {recipient}"})
    else:
        return jsonify({"success": False, "message": "Failed to send verification email. Please check SMTP settings."})
