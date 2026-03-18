from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from markupsafe import Markup
from core.utils import calculate_item_metrics, log_action, get_site_config, send_email_notification
from core.middleware import login_required, role_required
from core.db import get_items_collection, get_categories_collection, get_menus_collection, get_inventory_log_collection, get_undo_logs_collection, get_purchase_collection
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
        "timestamp": datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
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
    menus = list(menus_collection.find().sort("name", 1))
    
    return render_template('items.html', items=processed, role=session.get('role'), categories=categories, low_stock_threshold=threshold, menus=menus)

@inventory_bp.route('/items/add', methods=['POST'])
@login_required
def add_item():
    items_collection = get_items_collection()
    name = request.form.get('name')
    category = request.form.get('category')
    menu = request.form.get('menu', 'Standard')
    cost_price = float(request.form.get('cost_price', 0))
    retail_price = float(request.form.get('retail_price', 0))
    stock = int(request.form.get('stock', 0))
    sold = int(request.form.get('sold', 0))
    if name:
        res = items_collection.insert_one({
            "name": name, 
            "category": category, 
            "menu": menu, 
            "cost_price": cost_price, 
            "retail_price": retail_price, 
            "stock": stock, 
            "sold": sold,
            "active": True # Default to active
        })
        undo_id = save_undo_log("ADD_ITEM", res.inserted_id)
        log_action("ADD_ITEM", f"Added: {name}")
        undo_url = url_for('inventory.undo_action', undo_id=undo_id)
        flash(Markup(f"Item '{name}' added! <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "success")
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/edit/<id>', methods=['POST'])
@login_required
@role_required('owner')
def edit_item(id):
    items_collection = get_items_collection()
    name = request.form.get('name')
    category = request.form.get('category')
    menu = request.form.get('menu', 'Standard')
    cost_price = float(request.form.get('cost_price', 0))
    retail_price = float(request.form.get('retail_price', 0))
    stock = int(request.form.get('stock', 0))
    sold = int(request.form.get('sold', 0))
    if name:
        old_item = items_collection.find_one({'_id': ObjectId(id)})
        # Save state excluding _id
        prev_state = {k: v for k, v in old_item.items() if k != '_id'}
        undo_id = save_undo_log("EDIT_ITEM", id, prev_state)
        
        items_collection.update_one({'_id': ObjectId(id)}, {'$set': {"name": name, "category": category, "menu": menu, "cost_price": cost_price, "retail_price": retail_price, "stock": stock, "sold": sold}})
        log_action("EDIT_ITEM", f"Updated: {name}")
        undo_url = url_for('inventory.undo_action', undo_id=undo_id)
        flash(Markup(f"Item '{name}' updated! <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "success")
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/delete/<id>', methods=['POST'])
@login_required
@role_required('owner')
def delete_item(id):
    items_collection = get_items_collection()
    item = items_collection.find_one({'_id': ObjectId(id)})
    if item:
        undo_id = save_undo_log("DELETE_ITEM", id)
        # Soft Delete: Set active to False instead of deleting
        items_collection.update_one({'_id': ObjectId(id)}, {'$set': {"active": False}})
        log_action("DELETE_ITEM", f"Soft Deleted (Hidden): {item['name']}")
        undo_url = url_for('inventory.undo_action', undo_id=undo_id)
        flash(Markup(f"Item '{item['name']}' removed from master list. <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "info")
    return redirect(url_for('inventory.items'))

@inventory_bp.route('/items/reset/<id>', methods=['POST'])
@login_required
@role_required('owner')
def reset_item(id):
    items_collection = get_items_collection()
    item = items_collection.find_one({'_id': ObjectId(id)})
    if item:
        prev_state = {k: v for k, v in item.items() if k != '_id'}
        undo_id = save_undo_log("RESET_ITEM", id, prev_state)
        # Update: Also zero out cost and retail price as requested
        items_collection.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'stock': 0, 
                'sold': 0,
                'cost_price': 0,
                'retail_price': 0,
                'inventory_in': 0,
                'inventory_out': 0
            }}
        )
        log_action("RESET_ITEM", f"Reset stock/sold/prices for: {item['name']}")
        undo_url = url_for('inventory.undo_action', undo_id=undo_id)
        flash(Markup(f"Data for '{item['name']}' has been completely reset. <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "warning")
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
    if action == "STOCK_IN":
        return redirect(url_for('inventory.restock'))
    elif action == "SALE":
        return redirect(url_for('sales.sales_list'))
    return redirect(url_for('inventory.items'))

@inventory_bp.route("/restock")
@login_required
def restock():
    inventory_log_collection = get_inventory_log_collection()
    items_collection = get_items_collection()
    logs = list(inventory_log_collection.find({"type": "IN"}).sort("timestamp", -1))
    items_list = list(items_collection.find({"active": {"$ne": False}}).sort("name", 1))
    return render_template('inventory_io.html', logs=logs, items=items_list, role=session.get('role'))

@inventory_bp.route('/inventory/stock-in', methods=['POST'])
@login_required
def stock_in():
    items_collection = get_items_collection()
    inventory_log_collection = get_inventory_log_collection()
    item_id = request.form.get('item_id')
    qty = int(request.form.get('qty', 0))
    if item_id and qty > 0:
        item = items_collection.find_one({"_id": ObjectId(item_id)})
        if item:
            ts = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
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
            
            # Save undo log
            undo_id = save_undo_log("STOCK_IN", item_id, {"qty": qty, "item_name": item['name']})
            
            log_action("STOCK_IN", f"In: {qty} x {item['name']}")
            
            send_email_notification(
                "Stock In Recorded",
                f"New stock added: {qty} units of '{item['name']}' by {session.get('email')}.",
                notif_type="stock_in"
            )
            undo_url = url_for('inventory.undo_action', undo_id=undo_id)
            flash(Markup(f"Stock IN recorded! <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "success")
    return redirect(url_for('inventory.restock'))
