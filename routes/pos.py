from flask import Blueprint, render_template, request, session, jsonify
from core.db import get_items_collection, get_purchase_collection, get_inventory_log_collection, get_menus_collection
from core.middleware import login_required
from core.utils import log_action, send_email_notification, get_site_config
from extensions import socketio
from bson.objectid import ObjectId
from datetime import datetime

pos_bp = Blueprint('pos', __name__)

@pos_bp.route('/pos')
@login_required
def pos_view():
    items_collection = get_items_collection()
    menus_collection = get_menus_collection()
    
    # Only send active items with stock > 0 to POS
    items_list = list(items_collection.find({"active": {"$ne": False}, "stock": {"$gt": 0}}).sort("name", 1))
    
    # Get all menus that are actually used in the items
    used_menus = set()
    for item in items_list:
        menu = item.get('menu')
        if menu:
            used_menus.add(menu)
    
    # Also fetch defined menus from the menus collection to be safe
    defined_menus = [m['name'] for m in menus_collection.find()]
    for m in defined_menus:
        used_menus.add(m)
        
    final_menus = sorted(list(used_menus))
    
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
            "user": session.get('email')
        })
        
        logs_to_insert.append({
            "transaction_id": transaction_id,
            "item_name": item['name'],
            "type": "OUT",
            "qty": qty,
            "user": session.get('email'),
            "timestamp": ts,
            "new_stock": total_stock
        })
        
        # Deduct stock
        items_collection.update_one(
            {"_id": ObjectId(cart_item['_id'])}, 
            {"$inc": {"stock": -qty, "sold": qty, "inventory_out": qty}}
        )

        site_config = get_site_config()
        threshold = site_config.get('low_stock_threshold', 5)
        if 0 < total_stock <= threshold:
            send_email_notification(
                "Low Stock Alert!",
                f"CRITICAL: Item '{item['name']}' is now in low stock after a POS sale. Only {total_stock} units left! (Threshold: {threshold})",
                notif_type="low_stock"
            )
        elif total_stock == 0:
            send_email_notification(
                "Out of Stock Alert!",
                f"URGENT: Item '{item['name']}' is now OUT OF STOCK following a POS sale!",
                notif_type="low_stock"
            )
            
    if purchases_to_insert:
        purchase_collection.insert_many(purchases_to_insert)
    if logs_to_insert:
        inventory_log_collection.insert_many(logs_to_insert)
        
    log_action("POS_SALE", f"Transaction {transaction_id} completed. Total: ₱{total_amount}")
    
    send_email_notification(
        "New POS Sale",
        f"Transaction {transaction_id} recorded by {session.get('email')}. Total items: {sum(item['qty'] for item in cart)}. Total amount: ₱{total_amount}.",
        notif_type="sales"
    )

    socketio.emit('dashboard_update')

    return jsonify({
        "success": True, 
        "transaction_id": transaction_id,
        "total": total_amount,
        "cash_tendered": cash_tendered,
        "change_due": change_due,
        "message": "Checkout successful!"
    })
