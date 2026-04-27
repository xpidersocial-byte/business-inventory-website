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
        # Robust query for branch_id (string or ObjectId)
        for sale in purchase_col.find({"branch_id": {"$in": [b_id, ObjectId(b_id)]}, "status": "Sold"}):
            try:
                raw_ts = sale.get("timestamp") or sale.get("date")
                if not raw_ts: continue
                
                if isinstance(raw_ts, datetime):
                    log_date = raw_ts
                else:
                    ts_str = str(raw_ts)
                    parsed_dt = None
                    # Attempt robust parsing matching sales_summary logic
                    for fmt in ['%Y-%m-%d %I:%M:%S %p', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %I:%M %p']:
                        try:
                            parsed_dt = datetime.strptime(ts_str, fmt)
                            break
                        except ValueError: continue
                    if not parsed_dt: continue
                    log_date = parsed_dt
                
                if log_date >= week_ago: 
                    revenue += float(sale.get("total", 0))
            except Exception as e:
                print(f"Branch Revenue Error for {branch['name']}: {e}")
                continue
        branch["weekly_revenue"] = revenue
        
        # Staff Count
        branch["staff_count"] = users_col.count_documents({"branch_id": {"$in": [b_id, ObjectId(b_id)]}})
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

@branches_bp.route('/set-branch', methods=['POST'])
@login_required
def set_branch():
    branch_id = request.form.get('branch_id')
    role = session.get('role', 'cashier')
    
    # Security: If user is a cashier, they can only select their own assigned branch
    if role == 'cashier':
        users_col = get_users_collection()
        user = users_col.find_one({"email": session.get('email')})
        if user and user.get('branch_id'):
            branch_id = user.get('branch_id') # Force their assigned branch
        else:
            flash("You do not have an assigned branch. Please contact your manager.", "danger")
            return redirect(url_for('auth.logout'))

    if branch_id:
        session['branch_id'] = branch_id
        log_action("SWITCH_BRANCH", f"Switched to branch ID: {branch_id}")
        return redirect(url_for('dashboard.dashboard'))
    
    # If no branch_id, fallback to global (if owner)
    if role == 'owner':
        session.pop('branch_id', None)
        return redirect(url_for('dashboard.dashboard'))

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

@branches_bp.route('/branches/leaderboard')
@login_required
def leaderboard():
    branches_col = get_branches_collection()
    branches = list(branches_col.find({"active": True}))
    
    # --- Competitive Metrics ---
    purchase_col = get_purchase_collection()
    items_col = get_items_collection()
    users_col = get_users_collection()
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    
    leaderboard_data = []
    for branch in branches:
        b_id = str(branch["_id"])
        
        # 1. Revenue Score (Weight: 60%)
        revenue = 0
        for sale in purchase_col.find({"branch_id": {"$in": [b_id, ObjectId(b_id)]}, "status": "Sold"}):
            try:
                raw_ts = sale.get("timestamp") or sale.get("date")
                if not raw_ts: continue
                
                if isinstance(raw_ts, datetime):
                    log_date = raw_ts
                else:
                    ts_str = str(raw_ts)
                    parsed_dt = None
                    for fmt in ['%Y-%m-%d %I:%M:%S %p', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %I:%M %p']:
                        try:
                            parsed_dt = datetime.strptime(ts_str, fmt)
                            break
                        except ValueError: continue
                    if not parsed_dt: continue
                    log_date = parsed_dt
                
                if log_date >= week_ago: revenue += float(sale.get("total", 0))
            except: continue
        
        # 2. Activity Score (Weight: 20%)
        item_count = items_col.count_documents({"branch_id": {"$in": [b_id, ObjectId(b_id)]}})
        staff_count = users_col.count_documents({"branch_id": {"$in": [b_id, ObjectId(b_id)]}})
        
        # 3. Final Rank Calculation
        # Simple formula: (Revenue / 100) + (Items * 2) + (Staff * 5)
        score = (revenue / 100) + (item_count * 2) + (staff_count * 5)
        
        leaderboard_data.append({
            "name": branch["name"],
            "id": b_id,
            "revenue": revenue,
            "score": round(score, 1),
            "staff": staff_count,
            "items": item_count,
            "location": branch.get('location', 'Danao')
        })
    
    # Sort by score descending
    leaderboard_data = sorted(leaderboard_data, key=lambda x: x['score'], reverse=True)
    
    # Assign ranks
    for i, entry in enumerate(leaderboard_data):
        entry['rank'] = i + 1
        # Random growth indicator for UI effect
        entry['trend'] = random.choice(['up', 'down', 'steady'])

    return render_template('leaderboard.html', leaderboard=leaderboard_data, site_config=get_site_config())
