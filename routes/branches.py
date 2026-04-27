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

@branches_bp.route('/select-branch')
@login_required
def select_branch():
    # If user is a cashier, they should be restricted to their branch
    role = session.get('role', 'cashier')
    user_branch_id = session.get('branch_id')
    
    # Logic update: Cashiers are now forced to pass through the select-branch page 
    # to maintain the "Command Center" experience, but they are restricted to their assigned branch.
    # if role == 'cashier' and user_branch_id:
    #     session['branch_id'] = user_branch_id
    #     return redirect(url_for('dashboard.dashboard'))

    branches_col = get_branches_collection()
    items_col = get_items_collection()
    logs_col = get_inventory_log_collection()
    purchase_col = get_purchase_collection()
    users_col = get_users_collection()
    
    user = users_col.find_one({"email": session.get('email')})
    current_branch = None
    if user and user.get('branch_id'):
        current_branch = branches_col.find_one({"_id": ObjectId(user.get('branch_id'))})
    
    branches = list(branches_col.find({"active": True}).sort("name", 1))
    
    from core.db import get_menus_collection
    site_config = get_site_config()
    
    # Custom Reset Times
    now = datetime.now()
    
    fleet_reset = site_config.get('cc_fleet_reset', 'weekly')
    if fleet_reset == 'monthly': fleet_td = timedelta(days=30)
    elif fleet_reset == 'yearly': fleet_td = timedelta(days=365)
    else: fleet_td = timedelta(days=7)
    fleet_ago = now - fleet_td
    prev_fleet_ago = now - (fleet_td * 2)

    cashier_reset = site_config.get('cc_cashier_reset', 'weekly')
    if cashier_reset == 'daily': cashier_td = timedelta(days=1)
    elif cashier_reset == 'monthly': cashier_td = timedelta(days=30)
    elif cashier_reset == 'yearly': cashier_td = timedelta(days=365)
    else: cashier_td = timedelta(days=7)
    cashier_ago = now - cashier_td
    
    from core.db import get_menus_collection
    site_config = get_site_config()
    global_low = site_config.get('low_stock_threshold', 5)
    menus_col = get_menus_collection()
    menus_map = {m['name']: m.get('low_stock_threshold', global_low) for m in menus_col.find()}
    
    for branch in branches:
        b_id = str(branch['_id'])
        
        # Robust low stock check (matching dashboard logic)
        q = {"branch_id": {"$in": [b_id, ObjectId(b_id)]}, "active": {"$ne": False}}
        low_stock_count = 0
        branch_items = list(items_col.find(q))
        
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
                
                if stock <= float(low_threshold):
                    low_stock_count += 1
            except: continue
            
        # Map items for price lookups in sales processing
        items_map = {i['name']: i for i in branch_items}
        
        revenue = 0
        prev_revenue = 0
        profit = 0
        transactions = 0
        item_sales = {}
        # Helper to process sales from different collections
        def process_sales(cursor):
            nonlocal revenue, profit, transactions, prev_revenue
            for sale in cursor:
                try:
                    # Handle date/timestamp
                    ts = sale.get('timestamp') or sale.get('date')
                    dt = None
                    if isinstance(ts, datetime):
                        dt = ts
                    elif isinstance(ts, str):
                        for fmt in ['%Y-%m-%d %I:%M:%S %p', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                            try:
                                dt = datetime.strptime(ts.strip(), fmt)
                                break
                            except: continue
                    
                    if dt:
                        if dt >= fleet_ago:
                            item = items_map.get(sale['item_name'])
                            if item:
                                qty = float(sale.get('qty', 0))
                                retail = float(item.get('retail_price', 0))
                                cost = float(item.get('cost_price', 0))
                                
                                # Use actual sale total for revenue accuracy
                                sale_total = float(sale.get('total', qty * retail))
                                revenue += sale_total
                                profit += sale_total - (qty * cost)
                                transactions += 1
                                item_name = sale.get('item_name')
                                if item_name:
                                    item_sales[item_name] = item_sales.get(item_name, 0) + qty
                        elif dt >= prev_fleet_ago:
                            item = items_map.get(sale['item_name'])
                            if item:
                                qty = float(sale.get('qty', 0))
                                retail = float(item.get('retail_price', 0))
                                sale_total = float(sale.get('total', qty * retail))
                                prev_revenue += sale_total
                except: continue

        # Process only purchases to avoid double-counting with inventory logs
        process_sales(purchase_col.find({"branch_id": b_id, "status": "Sold"}))
        
        top_items = sorted(item_sales.items(), key=lambda x: x[1], reverse=True)[:5]
        branch['top_items'] = [{'name': name, 'qty': qty} for name, qty in top_items]
        
        dormant_item = None
        for item_name, item_data in items_map.items():
            if item_name not in item_sales and float(item_data.get('stock', 0)) > 0:
                dormant_item = item_name
                break
        
        branch['weekly_revenue'] = revenue
        branch['prev_weekly_revenue'] = prev_revenue
        branch['weekly_profit'] = profit
        branch['weekly_transactions'] = transactions
        branch['low_stock_count'] = low_stock_count

    # --- Cashier Gamification ---
    # Calculate top cashiers across all branches for this week
    cashier_stats = {}
    
    # We query purchases across all branches since cashiers are ranked globally
    all_weekly_purchases = list(purchase_col.find({
        # filter for this week if needed in query, but process_sales does it already
    }))

    for sale in all_weekly_purchases:
        try:
            ts = sale.get('date') or sale.get('timestamp')
            dt = None
            if isinstance(ts, datetime): 
                dt = ts
            elif isinstance(ts, str):
                # Try multiple formats, including the one from seed_branches (2026-04-22 02:02:07 AM)
                for fmt in ['%Y-%m-%d %I:%M:%S %p', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                    try:
                        dt = datetime.strptime(ts.strip(), fmt)
                        break
                    except: continue
            
            if dt and dt >= cashier_ago:
                email = sale.get('user', 'System')
                # Include social cashiers and ignore generic system accounts
                if email and '@' in email and 'system' not in email.lower():
                    if email not in cashier_stats:
                        c_user = users_col.find_one({"email": email})
                        c_name = email.split('@')[0].title()
                        if c_user and (c_user.get('first_name') or c_user.get('last_name')):
                            c_name = f"{c_user.get('first_name', '')} {c_user.get('last_name', '')}".strip()
                        
                        cashier_stats[email] = {
                            "email": email,
                            "name": c_name,
                            "sales_total": 0,
                            "transactions": 0
                        }
                    
                    cashier_stats[email]["sales_total"] += float(sale.get('total', 0))
                    cashier_stats[email]["transactions"] += 1
        except Exception as e:
            continue

    top_cashiers = sorted(cashier_stats.values(), key=lambda x: x['sales_total'], reverse=True)[:10]

    # --- Fleet Aggregation for Master View ---
    fleet_stats = {
        "revenue": sum(b.get('weekly_revenue', 0) for b in branches),
        "profit": sum(b.get('weekly_profit', 0) for b in branches),
        "transactions": sum(b.get('weekly_transactions', 0) for b in branches),
        "alerts": sum(b.get('low_stock_count', 0) for b in branches),
        "total_terminals": len(branches)
    }

    # Sort branches by revenue for gamification ranking
    branches = sorted(branches, key=lambda x: (x.get('weekly_revenue', 0), x['name']), reverse=True)

    return render_template('select_branch.html', 
                           branches=branches, 
                           user=user,
                           top_cashiers=top_cashiers,
                           fleet_stats=fleet_stats,
                           current_branch=current_branch,
                           current_branch_id=str(session.get('branch_id')) if session.get('branch_id') else None,
                           site_config=get_site_config())

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
    
    flash("Please select a branch to continue.", "warning")
    return redirect(url_for('branches.select_branch'))

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
