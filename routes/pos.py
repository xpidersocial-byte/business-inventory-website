from flask import Blueprint, render_template, request, session, jsonify
from core.db import get_items_collection, get_purchase_collection, get_inventory_log_collection, get_menus_collection, get_notifications_collection
from core.middleware import login_required
from core.utils import log_action, send_email_notification, get_site_config, trigger_notification, update_item_stock
from extensions import socketio
from bson.objectid import ObjectId
from datetime import datetime, timezone

pos_bp = Blueprint('pos', __name__)

@pos_bp.route('/pos')
@login_required
def pos_view():
    items_collection = get_items_collection()
    menus_collection = get_menus_collection()
    
    role = session.get('role', 'cashier')
    branch_id = session.get('branch_id')
    
    query = {"active": {"$ne": False}, "stock": {"$gt": 0}}
    if branch_id:
        query["branch_id"] = branch_id

    # Only send active items with stock > 0 to POS
    items_list = list(items_collection.find(query).sort("name", 1))
    
    # Get all distinct menus being used, or that are defined
    used_menus = set()
    for item in items_list:
        menu = item.get('menu') or item.get('category')
        if menu:
            used_menus.add(menu)
            
    # Also fetch defined menus from the menus collection to be safe
    menu_query = {"branch_id": branch_id} if branch_id else {}
    defined_menus = [m['name'] for m in menus_collection.find(menu_query) if 'name' in m]
    for m in defined_menus:
        used_menus.add(m)
        
    # Convert back to objects with 'name' property so the template loop {{ menu.name }} works
    final_menus = [{"name": m} for m in sorted(list(used_menus))]
    
    # Extract unique categories from items
    categories = list(set(item.get('category', 'Uncategorized') for item in items_list))
    categories.sort()

    # Pass everything to template
    return render_template('pos.html', items=items_list, categories=categories, menus=final_menus, role=session.get('role'))

@pos_bp.route('/pos/checkout', methods=['POST'])
@login_required
def pos_checkout():
    data = request.json
    cart = data.get('cart', [])
    cash_tendered = float(data.get('cash_tendered', 0))
    
    if not cart:
        return jsonify({"success": False, "message": "Cart is empty"}), 400

    items_collection = get_items_collection()
    purchase_collection = get_purchase_collection()
    inventory_log_collection = get_inventory_log_collection()
    
    total_amount = 0
    transaction_id = "TXN" + datetime.now().strftime("%Y%m%d%H%M%S")
    ts = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
    
    # Validation step
    for cart_item in cart:
        item = items_collection.find_one({"_id": ObjectId(cart_item['_id'])})
        if not item or item.get('stock', 0) < cart_item['qty']:
            return jsonify({"success": False, "message": f"Insufficient stock for {cart_item['name']}"}), 400
        total_amount += cart_item['qty'] * item['retail_price']
        
    if cash_tendered < total_amount:
        return jsonify({"success": False, "message": "Insufficient cash tendered"}), 400
        
    change_due = cash_tendered - total_amount
    
    # Processing step
    purchases_to_insert = []
    logs_to_insert = []
    
    for cart_item in cart:
        item = items_collection.find_one({"_id": ObjectId(cart_item['_id'])})
        qty = cart_item['qty']
        
        previous_stock = item.get('stock', 0)
        total_stock = previous_stock - qty
        unit_price = item.get('retail_price', 0)
        total = qty * unit_price
        
        purchases_to_insert.append({
            "transaction_id": transaction_id,
            "date": ts,
            "item_name": item['name'],
            "qty": qty,
            "previous_stock": previous_stock,
            "total_stock": total_stock,
            "unit_cost": unit_price,
            "total": total,
            "status": "Sold",
            "user": session.get('email'),
            "branch_id": session.get('branch_id')
        })
        
        logs_to_insert.append({
            "transaction_id": transaction_id,
            "item_name": item['name'],
            "type": "OUT",
            "qty": qty,
            "user": session.get('email'),
            "timestamp": ts,
            "new_stock": total_stock,
            "branch_id": session.get('branch_id')
        })
        
        # Deduct stock using centralized helper (handles notifications automatically)
        success, msg = update_item_stock(cart_item['_id'], qty, action_type="OUT")
        if not success:
            # This shouldn't happen due to validation step above, but good to have
            return jsonify({"success": False, "message": msg}), 400
            
    if purchases_to_insert:
        purchase_collection.insert_many(purchases_to_insert)
    if logs_to_insert:
        inventory_log_collection.insert_many(logs_to_insert)
        
    log_action("POS_SALE", f"Transaction {transaction_id} completed. Total: ₱{total_amount}")
    
    trigger_notification(
        "sale",
        "New POS Transaction",
        f"POS Sale: {sum(item['qty'] for item in cart)} items for ₱{total_amount:.2f}.",
        {"transaction_id": transaction_id, "total": total_amount, "items_count": len(cart)},
        priority="SUCCESS"
    )

    send_email_notification(
        "New POS Sale",
        f"Transaction {transaction_id} recorded by {session.get('email')}. Total items: {sum(item['qty'] for item in cart)}. Total amount: ₱{total_amount}.",
        notif_type="sales"
    )

    return jsonify({
        "success": True, 
        "transaction_id": transaction_id,
        "total": total_amount,
        "cash_tendered": cash_tendered,
        "change_due": change_due,
        "message": "Checkout successful!"
    })
