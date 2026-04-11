import os
import markdown
import re
import requests
from flask import Blueprint, render_template, request, session, jsonify, url_for, abort
from datetime import datetime, timedelta
from core.utils import calculate_item_metrics, parse_timestamp
from core.middleware import login_required
from core.db import get_items_collection, get_dev_updates_collection, get_inventory_log_collection, get_purchase_collection, get_notes_collection

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    items_collection = get_items_collection()
    dev_updates_collection = get_dev_updates_collection()
    inventory_log_collection = get_inventory_log_collection()
    
    view = request.args.get('view', 'weekly')
    raw_items = list(items_collection.find())
    
    processed_items = [calculate_item_metrics(item) for item in raw_items]
    item_details_map = {item['name']: item for item in processed_items}
    
    sales_logs = list(inventory_log_collection.find({"type": "OUT"}))
    in_logs = list(inventory_log_collection.find({"type": "IN"}))
    
    now = datetime.now()
    if view == 'daily':
        period_str = now.strftime('%Y-%m-%d')
        display_label = now.strftime('%b %d, %Y')
    elif view == 'weekly':
        start_of_week = now - timedelta(days=now.weekday())
        period_str = start_of_week.strftime('%Y-%m-%d')
        display_label = f"Week of {start_of_week.strftime('%b %d')}"
    elif view == 'yearly':
        period_str = now.strftime('%Y')
        display_label = now.strftime('%Y')
    else: # monthly default
        period_str = now.strftime('%Y-%m')
        display_label = now.strftime('%B %Y')

    if view == 'weekly':
        week_ago = now - timedelta(days=7)
        period_sales_logs = [log for log in sales_logs if (parse_timestamp(log.get('timestamp')) or datetime(2000,1,1)) >= week_ago]
        period_in_logs = [log for log in in_logs if (parse_timestamp(log.get('timestamp')) or datetime(2000,1,1)) >= week_ago]
    else:
        period_sales_logs = [log for log in sales_logs if log['timestamp'].startswith(period_str)]
        period_in_logs = [log for log in in_logs if log['timestamp'].startswith(period_str)]

    period_revenue = 0
    period_profit = 0
    period_qty = 0
    period_item_sales = {}

    refund_logs = [log for log in period_in_logs if 'refund' in log.get('reason', '').lower()]
    refund_by_name = {}
    for log in refund_logs:
        refund_by_name.setdefault(log.get('item_name'), 0)
        refund_by_name[log.get('item_name')] += log.get('qty', 0)

    sale_aggregates = {}
    for log in period_sales_logs:
        name = log.get('item_name')
        qty = log.get('qty', 0)
        if name in item_details_map:
            details = item_details_map[name]
            retail = float(details.get('retail_price', 0))
            cost = float(details.get('cost_price', 0))

            sale_aggregates.setdefault(name, {"qty": 0, "revenue": 0.0, "profit": 0.0, "retail": retail, "cost": cost})
            sale_aggregates[name]["qty"] += qty
            sale_aggregates[name]["revenue"] += qty * retail
            sale_aggregates[name]["profit"] += qty * (retail - cost)

    for name, data in sale_aggregates.items():
        refund_qty = refund_by_name.get(name, 0)
        adjusted_qty = max(data["qty"] - refund_qty, 0)
        if adjusted_qty <= 0:
            continue

        retail = data["retail"]
        cost = data["cost"]
        period_revenue += adjusted_qty * retail
        period_profit += adjusted_qty * (retail - cost)
        period_qty += adjusted_qty

        period_item_sales[name] = {
            "qty": adjusted_qty,
            "revenue": adjusted_qty * retail,
            "profit": adjusted_qty * (retail - cost),
            "name": name
        }

    period_inventory_added_value = sum(
        log.get('qty', 0) * float(item_details_map.get(log.get('item_name'), {}).get('cost_price', 0))
        for log in period_in_logs
        if log.get('item_name') in item_details_map and 'refund' not in log.get('reason', '').lower()
    )

    star_performers = sorted(period_item_sales.values(), key=lambda x: x['qty'], reverse=True)[:10]
    
    chart_data = sorted(period_item_sales.values(), key=lambda x: x['qty'], reverse=True)
    chart_labels = [f"{x['name']} (₱{x['revenue']:,.0f})" for x in chart_data[:10]]
    chart_values = [x['qty'] for x in chart_data[:10]]

    out_of_stock_items = [i for i in processed_items if i['status_label'] == 'Out of Stock']
    low_stock_items = [i for i in processed_items if i['status_label'] == 'Low Stock']
    warning_items = [i for i in processed_items if i['status_label'] == 'Warning']
    
    cold_stock = sorted([i for i in processed_items if i['stock'] > 0 and i.get('days_dormant', 0) > 30], key=lambda x: x.get('days_dormant', 0), reverse=True)[:5]
    sporadic_stock = sorted([i for i in processed_items if i['sold'] < 5], key=lambda x: x['sold'], reverse=True)[:5]

    top_item_name = "N/A"
    if star_performers:
        top_item_name = star_performers[0]['name']

    return render_template('dashboard.html', 
                           email=session['email'], 
                           role=session.get('role'), 
                           total_inventory_value=sum(i['inventory_value'] for i in processed_items),
                           period_inventory_value=period_inventory_added_value, 
                           monthly_revenue=period_revenue,
                           monthly_profit=period_profit,
                           monthly_qty=period_qty,
                           star_performers=star_performers,
                           top_item_name=top_item_name, 
                           current_month_display=display_label, 
                           chart_labels=chart_labels, 
                           chart_values=chart_values, 
                           out_of_stock_items=out_of_stock_items,
                           low_stock_items=low_stock_items,
                           warning_items=warning_items,
                           cold_stock=cold_stock,
                           sporadic_stock=sporadic_stock,
                           current_view=view)

@dashboard_bp.route('/global-search')
@login_required
def global_search():
    query = request.args.get('q', '')
    if not query or len(query) < 2:
        return jsonify({"results": []})

    results = []
    regex = re.compile(query, re.IGNORECASE)

    # 1. Search Items
    items_col = get_items_collection()
    found_items = items_col.find({"name": regex, "active": {"$ne": False}}).limit(5)
    for item in found_items:
        results.append({
            "title": item['name'],
            "subtitle": f"Stock: {item.get('stock', 0)} | Category: {item.get('category')}",
            "type": "Inventory Item",
            "icon": "bi-box-seam",
            "url": url_for('inventory.items') + "?search=" + item['name']
        })

    # 2. Search Sales (by item name in purchases)
    purchase_col = get_purchase_collection()
    found_sales = purchase_col.find({"item_name": regex}).sort("date", -1).limit(5)
    for sale in found_sales:
        results.append({
            "title": f"Sale: {sale['item_name']}",
            "subtitle": f"Qty: {sale['qty']} | Date: {sale['date']}",
            "type": "Transaction",
            "icon": "bi-receipt",
            "url": url_for('sales.sales_list')
        })

    # 3. Search Bulletin Board (Notes)
    notes_col = get_notes_collection()
    found_notes = notes_col.find({"$or": [{"title": regex}, {"content": regex}]}).limit(5)
    for note in found_notes:
        results.append({
            "title": note.get('title', 'Untitled Note'),
            "subtitle": note.get('category', 'Note'),
            "type": "Bulletin Board",
            "icon": "bi-clipboard-data",
            "url": url_for('bulletin.bulletin')
        })

    return jsonify({"results": results})
