from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from markupsafe import Markup
from core.utils import calculate_item_metrics, log_action, get_site_config, send_email_notification, trigger_notification, update_item_stock
from core.middleware import login_required, role_required
from core.db import get_items_collection, get_categories_collection, get_menus_collection, get_inventory_log_collection, get_undo_logs_collection, get_purchase_collection, get_users_collection, get_notifications_collection
from extensions import socketio
from bson.objectid import ObjectId
from datetime import datetime, timezone

inventory_bp = Blueprint('inventory', __name__)

def save_undo_log(action_type, item_id, previous_state=None):
    undo_logs_collection = get_undo_logs_collection()
    undo_id = str(ObjectId())
    undo_logs_collection.insert_one({
        "_id": ObjectId(undo_id),
        "undo_id": undo_id,
        "user": session.get('email'),
        "action": action_type,
        "item_id": str(item_id),
        "previous_state": previous_state,
        "timestamp": datetime.now(timezone.utc)
    })
    return undo_id

@inventory_bp.route('/items')
@login_required
def items():
    items_collection = get_items_collection()
    categories_collection = get_categories_collection()
    menus_collection = get_menus_collection()
    role = session.get('role', 'cashier')
    branch_id = session.get('branch_id')
    
    query = {"active": {"$ne": False}}
    if branch_id:
        query["branch_id"] = branch_id

    # Map branch names for Global View
    branches_map = {}
    if not branch_id:
        from core.db import get_db
        db = get_db()
        branches_list = list(db.branches.find({}, {"name": 1}))
        branches_map = {str(b['_id']): b['name'] for b in branches_list}

    raw_items = list(items_collection.find(query))
    processed = []
    for item in raw_items:
        m = calculate_item_metrics(item)
        if not branch_id:
            m['branch_name'] = branches_map.get(str(item.get('branch_id')), "Global")
        processed.append(m)
    
    # Filter categories and menus by branch
    cat_query = {}
    menu_query = {}
    if branch_id:
        cat_query["branch_id"] = branch_id
        menu_query["branch_id"] = branch_id
        
    categories = list(categories_collection.find(cat_query).sort("name", 1))
    menus = list(menus_collection.find(menu_query).sort("order", 1))
    
    site_config = get_site_config()
    threshold = site_config.get('low_stock_threshold', 5)
    
    # Update last view and clear persistent notifications for this section
    user_email = session.get('email')
    try:
        get_users_collection().update_one({"email": user_email}, {"$set": {"last_views.items": datetime.now(timezone.utc)}})
        # Clear persistent notifications for this section (branch-specific)
        item_notif_q = {"type": {"$in": ["item_added", "item_deleted", "item_edited", "item_reset"]}, "read_by": {"$ne": user_email}}
        if branch_id:
            item_notif_q["branch_id"] = branch_id
            
        get_notifications_collection().update_many(
            item_notif_q,
            {"$addToSet": {"read_by": user_email}}
        )
        socketio.emit('dashboard_update')
    except: pass
    
    return render_template('items.html', items=processed, role=session.get('role'), categories=categories, low_stock_threshold=threshold, menus=menus, site_config=get_site_config())



@inventory_bp.route('/legend')
@inventory_bp.route('/Legend')
@login_required
def legend():
    items_collection = get_items_collection()
    role = session.get('role', 'cashier')
    branch_id = session.get('branch_id')
    
    query = {"active": {"$ne": False}}
    if branch_id:
        query["branch_id"] = branch_id

    raw_items = list(items_collection.find(query))
    processed_items = [calculate_item_metrics(item) for item in raw_items]
    out_of_stock = [i for i in processed_items if i['status_label'] == 'Out of Stock']
    low_stock = [i for i in processed_items if i['status_label'] == 'Low Stock']
    warnings = [i for i in processed_items if i['status_label'] == 'Warning']

    try:
        user_email = session.get('email')
        get_users_collection().update_one(
            {"email": user_email},
            {"$set": {"last_views.legend": datetime.now(timezone.utc)}}
        )
        # Clear persistent notifications for stock alerts (branch-specific)
        stock_notif_q = {"type": "stock_alert", "read_by": {"$ne": user_email}}
        if branch_id:
            stock_notif_q["branch_id"] = branch_id
            
        get_notifications_collection().update_many(
            stock_notif_q,
            {"$addToSet": {"read_by": user_email}}
        )
        socketio.emit('dashboard_update')
    except: pass
    
    return render_template('legend.html', out_of_stock=out_of_stock, low_stock=low_stock, warnings=warnings, site_config=get_site_config())

@inventory_bp.route('/items/add', methods=['POST'])
@login_required
@role_required('cashier')
def add_item():
    items_collection = get_items_collection()
    data = request.get_json() if request.is_json else request.form
    name = data.get('name')
    category = data.get('category')
    menu = data.get('menu')
    cost_price = float(data.get('cost_price', 0))
    retail_price = float(data.get('retail_price', 0))
    stock = int(data.get('stock', 0))
    sold = int(data.get('sold', 0))
    barcode = data.get('barcode')
    low_threshold = data.get('low_threshold')
    low_threshold = int(low_threshold) if low_threshold and str(low_threshold).strip() != "" else None
    if name:
        res = items_collection.insert_one({
            "name": name, "barcode": barcode, "category": category, "menu": menu, 
            "cost_price": cost_price, "retail_price": retail_price, 
            "stock": stock, "sold": sold, "low_threshold": low_threshold, "active": True, 
            "branch_id": session.get('branch_id'),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })
        item_id = res.inserted_id
        undo_id = save_undo_log("ADD_ITEM", item_id)
        log_action("ADD_ITEM", f"Added: {name}")
        
        trigger_notification(
            "item_added",
            "New Item Added",
            f"'{name}' was added to the inventory.",
            {"item_id": str(item_id), "category": category},
            priority="SUCCESS"
        )

        if stock > 0:
            ts = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
            get_inventory_log_collection().insert_one({
                "item_name": name, "type": "IN", "qty": stock,
                "user": session.get('email', 'System'), "timestamp": ts,
                "new_stock": stock, "details": "Initial stock upon item creation",
                "branch_id": session.get('branch_id')
            })
        send_email_notification("New Item Added", f"A new inventory item was added.\n\nItem: {name}\nCategory: {category}\nMenu: {menu}\nCost: ₱{cost_price:.2f} | Retail: ₱{retail_price:.2f}\nAdded by: {session.get('email')}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}", notif_type="inventory")
        socketio.emit('dashboard_update')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({"success": True, "message": f"Item '{name}' added."})
            
        undo_url = url_for('inventory.undo_action', undo_id=undo_id)
        flash(Markup(f"Item '{name}' added! <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "success")
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/edit/<id>', methods=['POST'])
@login_required
@role_required('cashier')
def edit_item(id):
    items_collection = get_items_collection()
    data = request.get_json() if request.is_json else request.form
    name = data.get('name')
    category = data.get('category')
    menu = data.get('menu')
    cost_price = float(data.get('cost_price', 0))
    retail_price = float(data.get('retail_price', 0))
    barcode = data.get('barcode')
    low_threshold = data.get('low_threshold')
    low_threshold = int(low_threshold) if low_threshold and str(low_threshold).strip() != "" else None
    active_status = data.get('active') == 'on'
    
    if name:
        old_item = items_collection.find_one({'_id': ObjectId(id)})
        prev_state = {k: v for k, v in old_item.items() if k != '_id'}
        undo_id = save_undo_log("EDIT_ITEM", id, prev_state)
        items_collection.update_one({'_id': ObjectId(id)}, {'$set': {"name": name, "barcode": barcode, "category": category, "menu": menu, "cost_price": cost_price, "retail_price": retail_price, "low_threshold": low_threshold, "active": active_status, "updated_at": datetime.now(timezone.utc)}})
        log_action("EDIT_ITEM", f"Updated: {name}")
        trigger_notification(
            "item_edited",
            "Item Details Updated",
            f"Information for '{name}' was modified by {session.get('email')}.",
            {"item_id": id}
        )
        send_email_notification("Item Updated", f"An inventory item was edited.\n\nItem: {name}\nCategory: {category}\nCost: ₱{cost_price:.2f} | Retail: ₱{retail_price:.2f}\nEdited by: {session.get('email')}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}", notif_type="inventory")
        socketio.emit('dashboard_update')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({"success": True, "message": f"Item '{name}' updated."})
            
        undo_url = url_for('inventory.undo_action', undo_id=undo_id)
        flash(Markup(f"Item '{name}' updated! <a href='{url_for('inventory.undo_action', undo_id=undo_id)}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "info")
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/delete/<id>', methods=['POST'])
@login_required
@role_required('cashier')
def delete_item(id):
    items_collection = get_items_collection()
    item = items_collection.find_one({"_id": ObjectId(id)})
    if item:
        items_collection.update_one({"_id": ObjectId(id)}, {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}})
        log_action("DELETE_ITEM", f"Deleted: {item['name']}")
        trigger_notification(
            "item_deleted",
            "Item Removed",
            f"Item '{item['name']}' was soft-deleted from inventory.",
            {"item_id": id},
            priority="WARNING"
        )
        send_email_notification("Item Deleted", f"An inventory item was removed.\n\nItem: {item['name']}\nDeleted by: {session.get('email')}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}\n\nNote: This is a soft delete. The item can be restored.", notif_type="inventory")
        socketio.emit('dashboard_update')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({"success": True, "message": f"Item '{item['name']}' deleted."})
        flash(f"Item '{item['name']}' deleted.", "warning")
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/reset/<id>', methods=['POST'])
@login_required
@role_required('owner')
def reset_item(id):
    items_collection = get_items_collection()
    item = items_collection.find_one({"_id": ObjectId(id)})
    if item:
        items_collection.update_one({"_id": ObjectId(id)}, {"$set": {"stock": 0, "sold": 0, "inventory_in": 0, "inventory_out": 0, "updated_at": datetime.now(timezone.utc)}})
        log_action("RESET_ITEM", f"Reset metrics: {item['name']}")
        trigger_notification(
            "item_reset",
            "Item Metrics Reset",
            f"Performance metrics for '{item['name']}' were cleared.",
            {"item_id": id}
        )
        send_email_notification("Item Metrics Reset", f"An inventory item's performance metrics have been reset.\n\nItem: {item['name']}\nReset by: {session.get('email')}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}\n\nNote: Historical sales records in the ledger are preserved.", notif_type="inventory")
        socketio.emit('dashboard_update')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({"success": True, "message": f"Metrics for '{item['name']}' reset."})
        flash(f"Metrics for '{item['name']}' reset to zero.", "info")
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/restore/<id>', methods=['POST'])
@login_required
@role_required('owner')
def restore_item(id):
    items_collection = get_items_collection()
    item = items_collection.find_one({"_id": ObjectId(id)})
    if item:
        items_collection.update_one({"_id": ObjectId(id)}, {"$set": {"active": True, "updated_at": datetime.now(timezone.utc)}})
        log_action("RESTORE_ITEM", f"Restored: {item['name']}")
        trigger_notification(
            "item_added",
            "Item Restored",
            f"Item '{item['name']}' was restored to active inventory.",
            {"item_id": id}
        )
        socketio.emit('dashboard_update')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({"success": True, "message": f"Item '{item['name']}' restored."})
        flash(f"Item '{item['name']}' restored.", "success")
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/undo/<undo_id>')
@login_required
def undo_action(undo_id):
    undo_logs_collection = get_undo_logs_collection()
    items_collection = get_items_collection()
    log = undo_logs_collection.find_one({"undo_id": undo_id})
    if not log:
        flash("Undo record not found or expired.", "danger")
        return redirect(url_for('inventory.items'))
    
    action = log.get('action')
    item_id = log.get('item_id')
    
    if action == "ADD_ITEM":
        items_collection.delete_one({"_id": ObjectId(item_id)})
        flash("Action undone: Item removed.", "success")
    elif action == "EDIT_ITEM":
        prev_state = log.get('previous_state')
        items_collection.update_one({"_id": ObjectId(item_id)}, {"$set": prev_state})
        flash("Action undone: Changes reversed.", "success")
    elif action == "STOCK_IN":
        qty = log.get('previous_state', {}).get('qty', 0)
        items_collection.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": -qty, "inventory_in": -qty}})
        flash("Action undone: Stock entry reversed.", "success")
    elif action == "STOCK_OUT":
        qty = log.get('previous_state', {}).get('qty', 0)
        items_collection.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": qty, "inventory_out": -qty}})
        flash("Action undone: Stock reduction reversed.", "success")
    elif action == "SALE": return redirect(url_for('sales.sales_list'))
    
    undo_logs_collection.delete_one({"undo_id": undo_id})
    socketio.emit('dashboard_update')
    return redirect(url_for('inventory.items'))

@inventory_bp.route("/restock")
@login_required
@role_required('cashier')
def restock():
    inventory_log_collection = get_inventory_log_collection()
    items_collection = get_items_collection()
    role = session.get('role', 'cashier')
    branch_id = session.get('branch_id')
    
    item_query = {"active": {"$ne": False}}
    log_query = {"type": {"$in": ["IN", "DAMAGE"]}}
    
    if branch_id:
        item_query["branch_id"] = branch_id
        log_query["branch_id"] = branch_id

    items_list = list(items_collection.find(item_query).sort("name", 1))
    PER_PAGE = 50; page = max(1, int(request.args.get('page', 1)))
    total = inventory_log_collection.count_documents(log_query)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages); skip = (page - 1) * PER_PAGE
    logs = list(inventory_log_collection.find(log_query).sort("timestamp", -1).skip(skip).limit(PER_PAGE))
    
    user_email = session.get('email')
    try:
        get_users_collection().update_one({"email": user_email}, {"$set": {"last_views.restocks": datetime.now(timezone.utc)}})
        get_notifications_collection().update_many(
            {"type": {"$in": ["stock_in", "stock_out"]}, "read_by": {"$ne": user_email}},
            {"$addToSet": {"read_by": user_email}}
        )
        socketio.emit('dashboard_update')
    except: pass
    
    item_id = request.args.get('item_id')
    return render_template('inventory_io.html', logs=logs, items=items_list, role=session.get('role'), page=page, total_pages=total_pages, total=total, preselected_item_id=item_id, site_config=get_site_config())

@inventory_bp.route('/inventory/stock-in', methods=['POST'])
@login_required
@role_required('cashier')
def stock_in():
    items_collection = get_items_collection()
    data = request.get_json() if request.is_json else request.form
    item_id = data.get('item_id'); qty = int(data.get('qty', 0))
    inventory_log_collection = get_inventory_log_collection()
    if item_id and qty > 0:
        item = items_collection.find_one({"_id": ObjectId(item_id)})
        if item:
            ts = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'); new_stock = item.get('stock', 0) + qty
            # Use centralized helper for stock update and notifications
            success, msg = update_item_stock(item_id, qty, action_type="IN")
            if not success:
               flash(f"Error: {msg}", "danger")
               return redirect(url_for('inventory.restock'))

            inventory_log_collection.insert_one({"item_name": item['name'], "type": "IN", "qty": qty, "user": session['email'], "timestamp": ts, "new_stock": new_stock, "branch_id": session.get('branch_id')})
            undo_id = save_undo_log("STOCK_IN", item_id, {"qty": qty, "item_name": item['name']})
            log_action("STOCK_IN", f"In: {qty} x {item['name']}")
            
            trigger_notification(
                "stock_in",
                "Stock In Recorded",
                f"{qty} units of '{item['name']}' added to stock.",
                {"item_id": str(item_id), "qty": qty}
            )

            # Manual email notification for Stock IN specifically (optional, as helper handles critical ones)
            # send_email_notification(...) - Not strictly needed if it's just normal stock-in
            socketio.emit('dashboard_update')
            undo_url = url_for('inventory.undo_action', undo_id=undo_id)
            flash(Markup(f"Stock IN recorded! <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "success")
    return redirect(url_for('inventory.restock'))

@inventory_bp.route('/inventory/stock-out', methods=['POST'])
@login_required
@role_required('cashier')
def stock_out():
    items_collection = get_items_collection()
    data = request.get_json() if request.is_json else request.form
    item_id = data.get('item_id'); qty = int(data.get('qty', 0)); reason = data.get('reason', 'Damage/Loss')
    inventory_log_collection = get_inventory_log_collection()
    if item_id and qty > 0:
        item = items_collection.find_one({"_id": ObjectId(item_id)})
        if item:
            ts = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'); new_stock = item.get('stock', 0) - qty
            # Use centralized helper
            success, msg = update_item_stock(item_id, qty, action_type="OUT", reason=reason)
            if not success:
                flash(f"Error: {msg}", "danger")
                return redirect(url_for('inventory.restock'))

            inventory_log_collection.insert_one({"item_name": item['name'], "type": "DAMAGE", "qty": qty, "user": session['email'], "timestamp": ts, "new_stock": new_stock, "details": reason, "branch_id": session.get('branch_id')})
            undo_id = save_undo_log("STOCK_OUT", item_id, {"qty": qty, "item_name": item['name']})
            log_action("STOCK_OUT", f"Out: {qty} x {item['name']} ({reason})")
            
            trigger_notification(
                "stock_out",
                "Damage/Loss Recorded",
                f"{qty} units of '{item['name']}' removed due to {reason}.",
                {"item_id": str(item_id), "qty": qty, "reason": reason}
            )
            socketio.emit('dashboard_update')
            flash(Markup(f"Stock reduction recorded! <a href='{url_for('inventory.undo_action', undo_id=undo_id)}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "warning")
    return redirect(url_for('inventory.restock'))
