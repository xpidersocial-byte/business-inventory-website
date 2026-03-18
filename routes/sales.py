from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from markupsafe import Markup
from core.utils import calculate_item_metrics, log_action, get_site_config, send_email_notification
from core.middleware import login_required, role_required
from core.db import get_items_collection, get_purchase_collection, get_inventory_log_collection, get_undo_logs_collection
from bson.objectid import ObjectId
from datetime import datetime, timedelta

sales_bp = Blueprint('sales', __name__)

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

@sales_bp.route('/sales')
@login_required
@role_required('owner')
def sales_list():
    purchase_collection = get_purchase_collection()
    items_collection = get_items_collection()
    # Sort by date descending
    purchases = list(purchase_collection.find().sort("date", -1))
    items_list = list(items_collection.find({"active": {"$ne": False}}).sort("name", 1))
    return render_template('sales.html', purchases=purchases, items=items_list, role=session.get('role'))

@sales_bp.route('/sales/add', methods=['POST'])
@login_required
@role_required('owner')
def add_sale():
    items_collection = get_items_collection()
    purchase_collection = get_purchase_collection()
    inventory_log_collection = get_inventory_log_collection()
    item_id = request.form.get('item_id')
    qty = int(request.form.get('qty', 0))

    if item_id and qty > 0:
        item = items_collection.find_one({"_id": ObjectId(item_id)})
        if item:
            if item.get('stock', 0) >= qty:
                ts = datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
                previous_stock = item.get('stock', 0)
                total_stock = previous_stock - qty
                unit_price = item.get('retail_price', 0)
                total = qty * unit_price

                purchase_doc = {
                    "date": ts,
                    "item_name": item['name'],
                    "qty": qty,
                    "previous_stock": previous_stock,
                    "total_stock": total_stock,
                    "unit_cost": unit_price,
                    "total": total,
                    "status": "Sold",
                    "user": session.get('email')
                }
                res = purchase_collection.insert_one(purchase_doc)
                purchase_id = res.inserted_id

                items_collection.update_one({"_id": ObjectId(item_id)}, {"$inc": {"stock": -qty, "sold": qty, "inventory_out": qty}})
                inventory_log_collection.insert_one({
                    "item_name": item['name'],
                    "type": "OUT",
                    "qty": qty,
                    "user": session['email'],
                    "timestamp": ts,
                    "new_stock": total_stock
                })

                # Save undo log for SALE
                undo_id = save_undo_log("SALE", item_id, {"qty": qty, "item_name": item['name'], "purchase_id": str(purchase_id), "timestamp": ts})

                log_action("SALE", f"Sold: {qty} x {item['name']} for ₱{total}")

                send_email_notification(
                    "New Sale Recorded",
                    f"A new sale was recorded: {qty} x '{item['name']}' for {total}. Sold by {session.get('email')}. Remaining stock: {total_stock}",
                    notif_type="sales"
                )

                site_config = get_site_config()
                threshold = site_config.get('low_stock_threshold', 5)
                if 0 < total_stock <= threshold:
                    send_email_notification(
                        "Low Stock Alert!",
                        f"CRITICAL: Item '{item['name']}' is now in low stock after a sale. Only {total_stock} units left! (Threshold: {threshold})",
                        notif_type="low_stock"
                    )
                elif total_stock == 0:
                    send_email_notification(
                        "Out of Stock Alert!",
                        f"URGENT: Item '{item['name']}' is now OUT OF STOCK following a sale!",
                        notif_type="low_stock"
                    )
                
                undo_url = url_for('inventory.undo_action', undo_id=undo_id)
                flash(Markup(f"Sale recorded! Stock deducted for {item['name']}. <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "success")
            else:
                flash(f"Insufficient stock for {item['name']}!", "danger")
    return redirect(url_for('sales.sales_list'))

@sales_bp.route('/sales-summary')
@login_required
def sales_summary():
    inventory_log_collection = get_inventory_log_collection()
    items_collection = get_items_collection()
    view_type = request.args.get('view', 'yearly')
    now = datetime.now()
    current_year = now.year

    all_logs = list(inventory_log_collection.find({"type": "OUT"}))
    items_by_name = {item['name']: item for item in items_collection.find()}

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_revenue = [0] * 12
    monthly_profit = [0] * 12

    for log in all_logs:
        try:
            log_date = datetime.strptime(log['timestamp'], '%Y-%m-%d %I:%M:%S %p')
            if log_date.year == current_year:
                item = items_by_name.get(log['item_name'])
                if item:
                    qty = log.get('qty', 0)
                    month_idx = log_date.month - 1
                    monthly_revenue[month_idx] += qty * item.get('retail_price', 0)
                    profit_per_unit = abs(item.get('retail_price', 0) - item.get('cost_price', 0))
                    monthly_profit[month_idx] += qty * profit_per_unit
        except: continue

    weeks_labels = []
    weekly_revenue = []
    weekly_profit = []
    
    for i in range(11, -1, -1):
        start_date = now - timedelta(weeks=i+1)
        end_date = now - timedelta(weeks=i)
        weeks_labels.append(start_date.strftime('%-m/%-d/%y'))
        
        week_rev = 0
        week_prof = 0
        for log in all_logs:
            try:
                log_date = datetime.strptime(log['timestamp'], '%Y-%m-%d %I:%M:%S %p')
                if start_date <= log_date < end_date:
                    item = items_by_name.get(log['item_name'])
                    if item:
                        qty = log.get('qty', 0)
                        week_rev += qty * item.get('retail_price', 0)
                        profit_per_unit = abs(item.get('retail_price', 0) - item.get('cost_price', 0))
                        week_prof += qty * profit_per_unit
            except: continue
        
        weekly_revenue.append(week_rev)
        weekly_profit.append(week_prof)

    daily_labels = []
    daily_revenue = []
    daily_profit = []
    for i in range(29, -1, -1):
        target_date = now - timedelta(days=i)
        daily_labels.append(target_date.strftime('%-m/%-d/%y'))
        
        day_rev = 0
        day_prof = 0
        for log in all_logs:
            try:
                log_date = datetime.strptime(log['timestamp'], '%Y-%m-%d %I:%M:%S %p')
                if log_date.date() == target_date.date():
                    item = items_by_name.get(log['item_name'])
                    if item:
                        qty = log.get('qty', 0)
                        day_rev += qty * item.get('retail_price', 0)
                        profit_per_unit = abs(item.get('retail_price', 0) - item.get('cost_price', 0))
                        day_prof += qty * profit_per_unit
            except: continue
                
        daily_revenue.append(day_rev)
        daily_profit.append(day_prof)

    if view_type == 'weekly':
        total_revenue = sum(weekly_revenue)
        total_profit = sum(weekly_profit)
        avg_label = "Avg. Weekly Revenue"
        total_label = "Total Weekly Profit"
        data_points = [r for r in weekly_revenue if r > 0]
        avg_revenue = total_revenue / len(data_points) if data_points else 0
    elif view_type == 'daily':
        total_revenue = sum(daily_revenue)
        total_profit = sum(daily_profit)
        avg_label = "Avg. Daily Revenue"
        total_label = "Total Daily Profit"
        data_points = [r for r in daily_revenue if r > 0]
        avg_revenue = total_revenue / len(data_points) if data_points else 0
    else: # yearly/monthly
        total_revenue = sum(monthly_revenue)
        total_profit = sum(monthly_profit)
        avg_label = "Avg. Monthly Revenue"
        total_label = "Total Annual Profit"
        data_points = [r for r in monthly_revenue if r > 0]
        avg_revenue = total_revenue / len(data_points) if data_points else 0

    avg_profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0

    return render_template('sales_summary.html', 
                           email=session['email'],
                           role=session.get('role'),
                           months_labels=months, 
                           revenue_values=monthly_revenue, 
                           profit_values=monthly_profit,
                           weeks_labels=weeks_labels, 
                           weekly_revenue=weekly_revenue,
                           weekly_profit_values=weekly_profit,
                           daily_labels=daily_labels,
                           daily_revenue=daily_revenue,
                           daily_profit_values=daily_profit,
                           avg_revenue=avg_revenue,
                           total_profit=total_profit,
                           avg_label=avg_label,
                           total_label=total_label,
                           avg_profit_margin=round(avg_profit_margin, 1),
                           view_type=view_type,
                           now=now)
