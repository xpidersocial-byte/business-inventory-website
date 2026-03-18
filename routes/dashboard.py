from flask import Blueprint, render_template, request, session
from core.utils import calculate_item_metrics
from core.middleware import login_required
from core.db import get_items_collection, get_dev_updates_collection, get_inventory_log_collection
from datetime import datetime, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    items_collection = get_items_collection()
    dev_updates_collection = get_dev_updates_collection()
    inventory_log_collection = get_inventory_log_collection()
    
    view = request.args.get('view', 'weekly')
    raw_items = list(items_collection.find())
    
    # Pre-process items for lookups
    processed_items = [calculate_item_metrics(item) for item in raw_items]
    item_details_map = {item['name']: item for item in processed_items}
    
    # Get all logs for calculations
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

    # Filter logs based on view
    if view == 'weekly':
        week_ago = now - timedelta(days=7)
        period_sales_logs = [log for log in sales_logs if datetime.strptime(log['timestamp'], '%Y-%m-%d %I:%M:%S %p') >= week_ago]
        period_in_logs = [log for log in in_logs if datetime.strptime(log['timestamp'], '%Y-%m-%d %I:%M:%S %p') >= week_ago]
    else:
        period_sales_logs = [log for log in sales_logs if log['timestamp'].startswith(period_str)]
        period_in_logs = [log for log in in_logs if log['timestamp'].startswith(period_str)]

    # Calculate Period Metrics
    period_revenue = 0
    period_profit = 0
    period_qty = 0
    period_item_sales = {}

    for log in period_sales_logs:
        name = log.get('item_name')
        qty = log.get('qty', 0)
        if name in item_details_map:
            details = item_details_map[name]
            # Handle string to float conversion if necessary
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

    # Calculate Inventory Added Value
    period_inventory_added_value = sum(log.get('qty', 0) * float(item_details_map.get(log.get('item_name'), {}).get('cost_price', 0)) for log in period_in_logs if log.get('item_name') in item_details_map)

    # Top Performers
    star_performers = sorted(period_item_sales.values(), key=lambda x: x['qty'], reverse=True)[:5]
    
    # Chart Data
    chart_data = sorted(period_item_sales.values(), key=lambda x: x['qty'], reverse=True)
    chart_labels = [f"{x['name']} (₱{x['revenue']:,.0f})" for x in chart_data[:5]]
    chart_values = [x['qty'] for x in chart_data[:5]]

    # Dev Updates (Latest 3)
    dev_updates = list(dev_updates_collection.find().sort("timestamp", -1).limit(3))

    # Identify Stock Issues
    out_of_stock_items = [i for i in processed_items if i['status_label'] == 'Out of Stock']
    low_stock_items = [i for i in processed_items if i['status_label'] == 'Low Stock']
    warning_items = [i for i in processed_items if i['status_label'] == 'Warning']
    
    # Identify Cold Stock (No sales > 30 days) & Sporadic
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
                           dev_updates=dev_updates,
                           current_view=view)
