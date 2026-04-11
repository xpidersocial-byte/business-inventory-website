import os
import markdown
import re
import requests
from flask import Blueprint, render_template, request, session, jsonify, url_for, abort
from datetime import datetime, timedelta
from core.utils import calculate_item_metrics
from core.middleware import login_required
from core.db import get_items_collection, get_dev_updates_collection, get_inventory_log_collection, get_purchase_collection, get_notes_collection

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/docs/view/<path:filename>')
def view_markdown(filename):
    """Renders any .md file in the root directory as HTML for AI public access."""
    if not filename.endswith('.md'):
        abort(404)
        
    # Security: prevent path traversal by taking only the basename
    safe_filename = os.path.basename(filename)
    root_dir = os.path.dirname(os.path.abspath(__file__)) + "/.."
    file_path = os.path.join(root_dir, safe_filename)
    
    if not os.path.isfile(file_path):
        abort(404)
        
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
        
    # Convert markdown to HTML with common extensions
    html_body = markdown.markdown(text, extensions=['fenced_code', 'tables', 'nl2br', 'toc'])
    
    return render_template('md_view.html', 
                           filename=safe_filename, 
                           content=html_body,
                           email=session.get('email'),
                           role=session.get('role'))


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

    def parse_log_time(ts_str):
        for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %I:%M:%S %p', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %I:%M %p']:
            try:
                return datetime.strptime(ts_str, fmt)
            except ValueError:
                continue
        return None

    if view == 'weekly':
        week_ago = now - timedelta(days=7)
        period_sales_logs = []
        for log in sales_logs:
            dt = parse_log_time(log['timestamp'])
            if dt and dt >= week_ago:
                period_sales_logs.append(log)
        
        period_in_logs = []
        for log in in_logs:
            dt = parse_log_time(log['timestamp'])
            if dt and dt >= week_ago:
                period_in_logs.append(log)
    else:
        period_sales_logs = [log for log in sales_logs if log['timestamp'].startswith(period_str)]
        period_in_logs = [log for log in in_logs if log['timestamp'].startswith(period_str)]

    period_revenue = 0
    period_profit = 0
    period_qty = 0
    period_item_sales = {}

    for log in period_sales_logs:
        name = log.get('item_name')
        qty = log.get('qty', 0)
        if name in item_details_map:
            details = item_details_map[name]
            retail = float(details.get('retail_price', 0))
            cost = float(details.get('cost_price', 0))
            
            period_revenue += qty * retail
            period_profit += qty * (retail - cost)
            period_qty += qty
            
            if name not in period_item_sales:
                period_item_sales[name] = {"qty": 0, "revenue": 0, "profit": 0, "name": name}
            period_item_sales[name]["qty"] += qty
            period_item_sales[name]["revenue"] += qty * retail
            period_item_sales[name]["profit"] += qty * (retail - cost)

    period_inventory_added_value = sum(log.get('qty', 0) * float(item_details_map.get(log.get('item_name'), {}).get('cost_price', 0)) for log in period_in_logs if log.get('item_name') in item_details_map)

    star_performers = sorted(period_item_sales.values(), key=lambda x: x['qty'], reverse=True)[:10]
    
    chart_data = sorted(period_item_sales.values(), key=lambda x: x['qty'], reverse=True)
    chart_labels = [f"{x['name']} (₱{x['revenue']:,.0f})" for x in chart_data[:10]]
    chart_values = [x['qty'] for x in chart_data[:10]]

    out_of_stock_items = [i for i in processed_items if i['status_label'] == 'Out of Stock']
    low_stock_items = [i for i in processed_items if i['status_label'] == 'Low Stock']
    warning_items = [i for i in processed_items if i['status_label'] == 'Warning']
    
    cold_stock = sorted([i for i in processed_items if i['stock'] > 0 and i.get('days_dormant', 0) > 30], key=lambda x: x.get('days_dormant', 0), reverse=True)[:5]
    sporadic_stock = sorted([i for i in processed_items if i['sold'] < 5], key=lambda x: x['sold'], reverse=True)[:5]

    return render_template('dashboard.html', 
                           email=session['email'], 
                           role=session.get('role'), 
                           total_inventory_value=sum(i['inventory_value'] for i in processed_items),
                           period_inventory_value=period_inventory_added_value, 
                           monthly_revenue=period_revenue,
                           monthly_profit=period_profit,
                           monthly_qty=period_qty,
                           star_performers=star_performers,
                           top_item_name=star_performers[0]['name'] if star_performers else "N/A", 
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
