from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from markupsafe import Markup
from core.utils import calculate_item_metrics, log_action, get_site_config, send_email_notification
from core.middleware import login_required, role_required
from core.db import get_items_collection, get_categories_collection, get_menus_collection, get_inventory_log_collection, get_undo_logs_collection, get_purchase_collection, get_users_collection
from extensions import socketio
from bson.objectid import ObjectId
from datetime import datetime

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
        "timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    })
    return undo_id

@inventory_bp.route('/items')
@login_required
def items():
    items_collection = get_items_collection()
    categories_collection = get_categories_collection()
    menus_collection = get_menus_collection()
    
    # Filter for active items only
    raw_items = list(items_collection.find({"active": {"$ne": False}}))
    processed = [calculate_item_metrics(item) for item in raw_items]
    categories = list(categories_collection.find().sort("name", 1))
    
    site_config = get_site_config()
    threshold = site_config.get('low_stock_threshold', 5)
    menus = list(menus_collection.find().sort("order", 1))
    
    # Mark as read for this user
    try:
        get_users_collection().update_one(
            {"email": session.get('email')},
            {"$set": {"last_views.items": datetime.now()}}
        )
    except: pass
    
    return render_template('items.html', items=processed, role=session.get('role'), categories=categories, low_stock_threshold=threshold, menus=menus)

@inventory_bp.route('/legend')
@inventory_bp.route('/Legend')
@login_required
def legend():
    items_collection = get_items_collection()
    raw_items = list(items_collection.find({"active": {"$ne": False}}))
    processed_items = [calculate_item_metrics(item) for item in raw_items]
    
    # Categorize items for the legend/notifications page
    out_of_stock = [i for i in processed_items if i['status_label'] == 'Out of Stock']
    low_stock = [i for i in processed_items if i['status_label'] == 'Low Stock']
    warnings = [i for i in processed_items if i['status_label'] == 'Warning']
    
    # Mark as read for this user
    try:
        get_users_collection().update_one(
            {"email": session.get('email')},
            {"$set": {"last_views.legend": datetime.now()}}
        )
    except: pass

    return render_template('legend.html', 
                           out_of_stock=out_of_stock, 
                           low_stock=low_stock, 
                           warnings=warnings)

@inventory_bp.route('/items/add', methods=['POST'])
@login_required
def add_item():
    items_collection = get_items_collection()
    data = request.get_json() if request.is_json else request.form
    name = data.get('name')
    category = data.get('category')
    menu = data.get('menu') # No default to None
    cost_price = float(data.get('cost_price', 0))
    retail_price = float(data.get('retail_price', 0))
    stock = int(data.get('stock', 0))
    sold = int(data.get('sold', 0))
    
    new_id = None
    if name:
        res = items_collection.insert_one({
            "name": name, 
            "category": category, 
            "menu": menu, 
            "cost_price": cost_price, 
            "retail_price": retail_price, 
            "stock": stock, 
            "sold": sold,
            "active": True, # Default to active
            "created_at": datetime.now()
        })
        new_id = str(res.inserted_id)
        
        # Log initial stock movement if provided
        if stock > 0:
            get_inventory_log_collection().insert_one({
                "item_name": name, 
                "type": "IN", 
                "qty": stock, 
                "user": session.get('email'), 
                "timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
                "new_stock": stock,
                "reason": "Initial stock on creation"
            })
            # Trigger real-time update if stock was added
            socketio.emit('dashboard_update')

        undo_id = save_undo_log("ADD_ITEM", new_id)
        log_action("ADD_ITEM", f"Added: {name} (Initial Stock: {stock})")
        send_email_notification(
            "New Item Added",
            f"A new inventory item was added.\n\nItem: {name}\nCategory: {category}\nMenu: {menu}\nInitial Stock: {stock}\nCost: ₱{cost_price:.2f} | Retail: ₱{retail_price:.2f}\nAdded by: {session.get('email')}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}",
            notif_type="inventory"
        )
        undo_url = url_for('inventory.undo_action', undo_id=undo_id)
        flash(Markup(f"Item '{name}' added! <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "success")
    
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True, "id": new_id})
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/edit/<id>', methods=['POST'])
@login_required
@role_required('owner')
def edit_item(id):
    items_collection = get_items_collection()
    data = request.get_json() if request.is_json else request.form
    name = data.get('name')
    category = data.get('category')
    menu = data.get('menu') # No default to None
    cost_price = float(data.get('cost_price', 0))
    retail_price = float(data.get('retail_price', 0))
    if name:
        old_item = items_collection.find_one({'_id': ObjectId(id)})
        # Save state excluding _id
        prev_state = {k: v for k, v in old_item.items() if k != '_id'}
        undo_id = save_undo_log("EDIT_ITEM", id, prev_state)
        
        items_collection.update_one({'_id': ObjectId(id)}, {'$set': {"name": name, "category": category, "menu": menu, "cost_price": cost_price, "retail_price": retail_price}})
        log_action("EDIT_ITEM", f"Updated: {name}")
        send_email_notification(
            "Item Updated",
            f"An inventory item was edited.\n\nItem: {name}\nCategory: {category}\nCost: ₱{cost_price:.2f} | Retail: ₱{retail_price:.2f}\nEdited by: {session.get('email')}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}",
            notif_type="inventory"
        )
        undo_url = url_for('inventory.undo_action', undo_id=undo_id)
        flash(Markup(f"Item '{name}' updated! <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "success")
    
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True})
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_item(id):
    items_collection = get_items_collection()
    try:
        oid = ObjectId(id)
    except:
        return jsonify({"success": False, "error": "Invalid ID format"}), 400

    item = items_collection.find_one({'_id': oid})
    if item:
        undo_id = save_undo_log("DELETE_ITEM", id)
        # Soft Delete: Set active to False instead of deleting
        items_collection.update_one({'_id': oid}, {'$set': {"active": False}})
        log_action("DELETE_ITEM", f"Soft Deleted (Hidden): {item['name']}")
        send_email_notification(
            "Item Deleted",
            f"An inventory item was removed.\n\nItem: {item['name']}\nDeleted by: {session.get('email')}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}\n\nNote: This is a soft delete. The item can be restored.",
            notif_type="inventory"
        )
        undo_url = url_for('inventory.undo_action', undo_id=undo_id)
        flash(Markup(f"Item '{item['name']}' removed from master list. <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "info")
    
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True})
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/reset/<id>', methods=['POST'])
@login_required
@role_required('owner')
def reset_item(id):
    items_collection = get_items_collection()
    try:
        oid = ObjectId(id)
    except:
        return jsonify({"success": False, "error": "Invalid ID format"}), 400

    item = items_collection.find_one({'_id': oid})
    if item:
        prev_state = {k: v for k, v in item.items() if k != '_id'}
        undo_id = save_undo_log("RESET_ITEM", id, prev_state)
        # Zero out performance counters but keep prices to preserve item definition
        items_collection.update_one(
            {'_id': oid},
            {'$set': {
                'stock': 0, 
                'sold': 0,
                'inventory_in': 0,
                'inventory_out': 0
            }}
        )
        log_action("RESET_ITEM", f"Reset counters for: {item['name']}")
        send_email_notification(
            "Item Metrics Reset",
            f"An inventory item's performance metrics have been reset.\n\nItem: {item['name']}\nReset by: {session.get('email')}\nTime: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}\n\nNote: Historical sales records in the ledger are preserved.",
            notif_type="inventory"
        )
        undo_url = url_for('inventory.undo_action', undo_id=undo_id)
        flash(Markup(f"Data for '{item['name']}' has been completely reset. <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "warning")
    
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({"success": True})
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/undo/<undo_id>')
@login_required
def undo_action(undo_id):
    undo_logs_collection = get_undo_logs_collection()
    items_collection = get_items_collection()
    inventory_log_collection = get_inventory_log_collection()
    purchase_collection = get_purchase_collection()
    
    log = undo_logs_collection.find_one({"undo_id": undo_id})
    if not log:
        flash("Undo action expired or not found.", "danger")
        return redirect(url_for('inventory.items'))
    
    action = log['action']
    item_id = log['item_id']
    prev_state = log.get('previous_state')
    
    success = False
    message = ""
    
    try:
        if action == "ADD_ITEM":
            # Undo Add = Delete
            items_collection.delete_one({"_id": ObjectId(item_id)})
            success = True
            message = "Added item removed successfully."
        elif action == "EDIT_ITEM" or action == "RESET_ITEM":
            # Undo Edit/Reset = Restore previous state
            if prev_state:
                items_collection.update_one({"_id": ObjectId(item_id)}, {"$set": prev_state})
                success = True
                message = "Changes reverted successfully."
        elif action == "DELETE_ITEM":
            # Undo Delete = Set active: True
            items_collection.update_one({"_id": ObjectId(item_id)}, {"$set": {"active": True}})
            success = True
            message = "Item restored successfully."
        elif action == "STOCK_IN":
            # Undo Stock In = Revert stock increment
            if prev_state and 'qty' in prev_state:
                qty = prev_state['qty']
                items_collection.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": -qty, "inventory_in": -qty}})
                # Remove the IN log too
                inventory_log_collection.delete_one({"item_name": prev_state['item_name'], "type": "IN", "timestamp": log['timestamp']})
                success = True
                message = "Stock addition reverted successfully."
        elif action == "STOCK_OUT":
            # Undo Stock Out (Damage) = Revert stock decrement
            if prev_state and 'qty' in prev_state:
                qty = prev_state['qty']
                items_collection.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": qty, "inventory_out": -qty}})
                # Remove the DAMAGE log
                inventory_log_collection.delete_one({"item_name": prev_state['item_name'], "type": "DAMAGE", "timestamp": log['timestamp']})
                success = True
                message = "Inventory adjustment (Damage/Loss) reverted successfully."
        elif action == "SALE":
            # Undo Sale = Revert stock deduction, remove purchase record and log
            if prev_state and 'qty' in prev_state:
                qty = prev_state['qty']
                purchase_id = prev_state.get('purchase_id')
                items_collection.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": qty, "sold": -qty, "inventory_out": -qty}})
                if purchase_id:
                    purchase_collection.delete_one({"_id": ObjectId(purchase_id)})
                inventory_log_collection.delete_one({"item_name": prev_state['item_name'], "type": "OUT", "timestamp": log['timestamp']})
                success = True
                message = "Sale transaction reverted successfully."
    except Exception as e:
        message = f"Error during undo: {str(e)}"
        success = False
            
    if success:
        undo_logs_collection.delete_one({"undo_id": undo_id})
        log_action("UNDO_ACTION", f"Undone: {action} for Item {item_id}")
        flash(message, "success")
    else:
        flash(message or "Failed to undo action.", "danger")
        
    # Redirect based on where the action likely happened
    if action in ["STOCK_IN", "STOCK_OUT"]:
        return redirect(url_for('inventory.restock'))
    elif action == "SALE":
        return redirect(url_for('sales.sales_list'))
    return redirect(url_for('inventory.items'))

@inventory_bp.route("/restock")
@login_required
def restock():
    inventory_log_collection = get_inventory_log_collection()
    items_collection = get_items_collection()
    items_list = list(items_collection.find({"active": {"$ne": False}}).sort("name", 1))

    PER_PAGE = 50
    page = max(1, int(request.args.get('page', 1)))
    total = inventory_log_collection.count_documents({"type": {"$in": ["IN", "DAMAGE"]}})
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    skip = (page - 1) * PER_PAGE

    logs = list(inventory_log_collection.find({"type": {"$in": ["IN", "DAMAGE"]}})
                .sort("timestamp", -1).skip(skip).limit(PER_PAGE))
    # Mark as read for this user
    try:
        get_users_collection().update_one(
            {"email": session.get('email')},
            {"$set": {"last_views.restocks": datetime.now()}}
        )
    except: pass

    item_id = request.args.get('item_id')
    return render_template('inventory_io.html', logs=logs, items=items_list,
                           role=session.get('role'), page=page, total_pages=total_pages, total=total, preselected_item_id=item_id)


@inventory_bp.route('/inventory/stock-in', methods=['POST'])
@login_required
def stock_in():
    items_collection = get_items_collection()
    data = request.get_json() if request.is_json else request.form
    item_id = data.get('item_id')
    qty = int(data.get('qty', 0))
    inventory_log_collection = get_inventory_log_collection()
    if item_id and qty > 0:
        item = items_collection.find_one({"_id": ObjectId(item_id)})
        if item:
            ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            new_stock = item.get('stock', 0) + qty
            items_collection.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": qty, "inventory_in": qty}})
            inventory_log_collection.insert_one({
                "item_name": item['name'], 
                "type": "IN", 
                "qty": qty, 
                "user": session['email'], 
                "timestamp": ts,
                "new_stock": new_stock
            })
            
            undo_id = save_undo_log("STOCK_IN", item_id, {"qty": qty, "item_name": item['name']})
            
            log_action("STOCK_IN", f"In: {qty} x {item['name']}")
            
            send_email_notification(
                "Stock In Recorded",
                f"New stock added: {qty} units of '{item['name']}' by {session.get('email')}.",
                notif_type="stock_in"
            )
            
            # Real-time trigger for sidebar badges
            socketio.emit('dashboard_update')
            
            undo_url = url_for('inventory.undo_action', undo_id=undo_id)
            flash(Markup(f"Stock IN recorded! <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "success")
    return redirect(url_for('inventory.restock'))

@inventory_bp.route('/api/items/sync')
@login_required
def api_sync_items():
    try:
        items_collection = get_items_collection()
        # Fetch all active items, only return minimal fields to save bandwidth
        raw_items = list(items_collection.find({"active": {"$ne": False}}, {
            "name": 1, "category": 1, "menu": 1, "retail_price": 1, "stock": 1, "sold": 1
        }))
        
        # Process them to ensure they have a string _id for PouchDB
        processed = []
        for item in raw_items:
            if '_id' in item:
                item['_id'] = str(item['_id'])
            processed.append(item)
            
        return jsonify(processed)
    except Exception as e:
        import traceback
        error_msg = f"Sync API Error: {str(e)}"
        print(f"[ERROR] {error_msg}")
        print(traceback.format_exc())
        return jsonify({"error": error_msg, "status": "failed"}), 500


@inventory_bp.route('/inventory/stock-out', methods=['POST'])
@login_required
def stock_out():
    """Handles damages and losses."""
    items_collection = get_items_collection()
    data = request.get_json() if request.is_json else request.form
    item_id = data.get('item_id')
    qty = int(data.get('qty', 0))
    reason = data.get('reason', 'Damage/Loss')
    inventory_log_collection = get_inventory_log_collection()
    
    if item_id and qty > 0:
        item = items_collection.find_one({"_id": ObjectId(item_id)})
        if item:
            if item.get('stock', 0) >= qty:
                ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
                new_stock = item.get('stock', 0) - qty
                items_collection.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": -qty, "inventory_out": qty}})
                inventory_log_collection.insert_one({
                    "item_name": item['name'], 
                    "type": "DAMAGE", 
                    "qty": qty, 
                    "user": session['email'], 
                    "timestamp": ts,
                    "new_stock": new_stock,
                    "reason": reason
                })
                
                # Save undo log
                undo_id = save_undo_log("STOCK_OUT", item_id, {"qty": qty, "item_name": item['name']})
                
                log_action("DAMAGE_RECORDED", f"Damage/Loss: {qty} x {item['name']} - Reason: {reason}")
                
                send_email_notification(
                    "Damage/Loss Recorded",
                    f"Stock reduction recorded: {qty} units of '{item['name']}' removed due to {reason}. Recorded by {session.get('email')}.",
                    notif_type="stock_out"
                )
                
                # Real-time trigger for sidebar badges
                socketio.emit('dashboard_update')
                
                undo_url = url_for('inventory.undo_action', undo_id=undo_id)
                flash(Markup(f"Damage/Loss of '{item['name']}' recorded! Stock deducted. <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "warning")
            else:
                flash(f"Insufficient stock for {item['name']} to record damage!", "danger")
    return redirect(url_for('inventory.restock'))
