from flask import Blueprint, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from markupsafe import Markup
from core.utils import calculate_item_metrics, log_action, get_site_config, send_email_notification, parse_timestamp
from core.middleware import login_required, role_required
from core.db import get_items_collection, get_purchase_collection, get_inventory_log_collection, get_undo_logs_collection, get_users_collection
from extensions import socketio
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import io
import os

# Reporting Libraries
from fpdf import FPDF
import pandas as pd
from docx import Document
from docx.shared import Inches

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
        "timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    })
    return undo_id

@sales_bp.route('/sales')
@login_required
def sales_list():
    purchase_collection = get_purchase_collection()
    items_collection = get_items_collection()
    items_list = list(items_collection.find({"active": {"$ne": False}}).sort("name", 1))

    PER_PAGE = 50
    page = max(1, int(request.args.get('page', 1)))
    total = purchase_collection.count_documents({})
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages)
    skip = (page - 1) * PER_PAGE

    purchases = list(purchase_collection.find().sort("date", -1).skip(skip).limit(PER_PAGE))
    
    # Mark as read for this user
    try:
        get_users_collection().update_one(
            {"email": session.get('email')},
            {"$set": {"last_views.sales": datetime.now()}}
        )
    except: pass

    return render_template('sales.html', purchases=purchases, items=items_list,
                           role=session.get('role'), page=page, total_pages=total_pages, total=total)


@sales_bp.route('/sales/add', methods=['POST'])
@login_required
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
                ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
                previous_stock = item.get('stock', 0)
                total_stock = previous_stock - qty
                unit_price = item.get('retail_price', 0)
                total = qty * unit_price

                purchase_doc = {
                    "date": ts,
                    "item_id": str(item['_id']),
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

                undo_id = save_undo_log("SALE", item_id, {"qty": qty, "item_name": item['name'], "purchase_id": str(purchase_id), "timestamp": ts})
                log_action("SALE", f"Sold: {qty} x {item['name']} for ₱{total}")

                send_email_notification("New Sale Recorded", f"A new sale was recorded: {qty} x '{item['name']}' for {total}.", notif_type="sales")
                
                undo_url = url_for('inventory.undo_action', undo_id=undo_id)
                flash(Markup(f"Sale recorded! Stock deducted for {item['name']}. <a href='{undo_url}' class='alert-link fw-bold ms-2 text-decoration-underline'>Undo</a>"), "success")
            else:
                flash(f"Insufficient stock for {item['name']}!", "danger")
    return redirect(url_for('sales.sales_list'))

@sales_bp.route('/sales/refund/<id>', methods=['POST'])
@login_required
def refund_sale(id):
    if session.get('role') == 'owner':
        return jsonify({"success": False, "error": "Refunds are restricted to cashier access."}), 403

    purchase_collection = get_purchase_collection()
    items_collection = get_items_collection()
    inventory_log_collection = get_inventory_log_collection()
    
    try:
        oid = ObjectId(id)
    except:
        return jsonify({"success": False, "error": "Invalid ID format"}), 400

    purchase = purchase_collection.find_one({'_id': oid})
    if not purchase:
        return jsonify({"success": False, "error": "Sale not found"}), 404
    
    if purchase.get('status') == 'Refunded':
        return jsonify({"success": False, "error": "Sale already refunded"}), 400
    
    item_name = purchase['item_name']
    qty = purchase['qty']
    item_id = purchase.get('item_id')
    
    # 1. Update purchase status
    purchase_collection.update_one({'_id': oid}, {'$set': {'status': 'Refunded', 'refunded_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}})
    
    # 2. Return stock to item
    item = None
    if item_id:
        try:
            item = items_collection.find_one({'_id': ObjectId(item_id)})
        except:
            item = None
    if not item:
        item = items_collection.find_one({'name': item_name})
    if item:
        new_stock = item.get('stock', 0) + qty
        items_collection.update_one(
            {'_id': item['_id']}, 
            {'$inc': {'stock': qty, 'sold': -qty, 'inventory_out': -qty}}
        )
        
        # 3. Log the inventory return
        ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        inventory_log_collection.insert_one({
            "item_name": item_name,
            "type": "IN",
            "qty": qty,
            "user": session.get('email'),
            "timestamp": ts,
            "new_stock": new_stock,
            "reason": f"Refund of transaction {id}"
        })
        
        log_action("SALE_REFUND", f"Refunded: {qty} x {item_name} from sale {id}")
        
        send_email_notification(
            "Sale Refunded",
            f"A sale transaction was refunded.\n\nItem: {item_name}\nQuantity: {qty}\nRefunded by: {session.get('email')}\nTime: {ts}",
            notif_type="sales"
        )
        
        # Trigger real-time updates
        socketio.emit('dashboard_update')
        
        return jsonify({"success": True, "message": "Sale refunded successfully"})
    
    return jsonify({"success": False, "error": "Item not found in inventory"})

@sales_bp.route('/sales-summary')
@login_required
def sales_summary():
    inventory_log_collection = get_inventory_log_collection()
    items_collection = get_items_collection()
    view_type = request.args.get('view', 'monthly')
    now = datetime.now()
    current_year = now.year

    # Shared parse_timestamp from core.utils is used below

    all_logs = list(inventory_log_collection.find({"type": {"$in": ["OUT", "IN"]}}))
    items_by_name = {item['name']: item for item in items_collection.find()}

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_revenue = [0.0] * 12
    monthly_profit = [0.0] * 12
    weekly_revenue = []
    weekly_profit = []
    weeks_labels = []
    daily_labels = []
    daily_revenue = []
    daily_profit = []

    for log in all_logs:
        timestamp = log.get('timestamp')
        if not timestamp:
            continue
        log_date = parse_timestamp(timestamp)
        if not log_date or log_date.year != current_year:
            continue

        log_type = log.get('type')
        reason = str(log.get('reason', '')).lower()
        if log_type == 'IN' and 'refund' not in reason:
            continue

        item = items_by_name.get(log.get('item_name'))
        if not item:
            continue

        qty = log.get('qty', 0)
        sign = -1 if log_type == 'IN' and 'refund' in reason else 1
        month_idx = log_date.month - 1
        revenue = sign * qty * item.get('retail_price', 0)
        profit = sign * qty * (item.get('retail_price', 0) - item.get('cost_price', 0))
        monthly_revenue[month_idx] += revenue
        monthly_profit[month_idx] += profit

    for i in range(11, -1, -1):
        start_date = now - timedelta(weeks=i+1)
        end_date = now - timedelta(weeks=i)
        weeks_labels.append(start_date.strftime('%-m/%-d/%y'))

        week_rev = 0.0
        week_prof = 0.0
        for log in all_logs:
            timestamp = log.get('timestamp')
            if not timestamp:
                continue
            log_date = parse_timestamp(timestamp)
            if not log_date or not (start_date <= log_date < end_date):
                continue

            log_type = log.get('type')
            reason = str(log.get('reason', '')).lower()
            if log_type == 'IN' and 'refund' not in reason:
                continue

            item = items_by_name.get(log.get('item_name'))
            if not item:
                continue

            qty = log.get('qty', 0)
            sign = -1 if log_type == 'IN' and 'refund' in reason else 1
            revenue = sign * qty * item.get('retail_price', 0)
            profit = sign * qty * (item.get('retail_price', 0) - item.get('cost_price', 0))
            week_rev += revenue
            week_prof += profit

        weekly_revenue.append(week_rev)
        weekly_profit.append(week_prof)

    for i in range(29, -1, -1):
        target_date = now - timedelta(days=i)
        daily_labels.append(target_date.strftime('%-m/%-d/%y'))

        day_rev = 0.0
        day_prof = 0.0
        for log in all_logs:
            timestamp = log.get('timestamp')
            if not timestamp:
                continue
            log_date = parse_timestamp(timestamp)
            if not log_date or log_date.date() != target_date.date():
                continue

            log_type = log.get('type')
            reason = str(log.get('reason', '')).lower()
            if log_type == 'IN' and 'refund' not in reason:
                continue

            item = items_by_name.get(log.get('item_name'))
            if not item:
                continue

            qty = log.get('qty', 0)
            sign = -1 if log_type == 'IN' and 'refund' in reason else 1
            revenue = sign * qty * item.get('retail_price', 0)
            profit = sign * qty * (item.get('retail_price', 0) - item.get('cost_price', 0))
            day_rev += revenue
            day_prof += profit

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
    elif view_type == 'monthly':
        current_month_rev = monthly_revenue[now.month - 1]
        current_month_prof = monthly_profit[now.month - 1]
        total_revenue = current_month_rev
        total_profit = current_month_prof
        avg_label = "Current Month Revenue"
        total_label = "Current Month Profit"
        avg_revenue = current_month_rev
    else:
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

@sales_bp.route('/sales/generate-report')
@login_required
def generate_report():
    view_type = request.args.get('view', 'monthly')
    format_type = request.args.get('format', 'pdf')
    now = datetime.now()
    
    try:
        inventory_log_collection = get_inventory_log_collection()
        items_collection = get_items_collection()
        all_logs = list(inventory_log_collection.find({"type": {"$in": ["OUT", "IN"]}}))
        items_by_name = {item['name']: item for item in items_collection.find()}
        
        report_data = []
        
        # Filter data based on view_type
        for log in all_logs:
            try:
                timestamp = log.get('timestamp')
                if not timestamp: continue
                
                log_date = None
                for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %I:%M %p']:
                    try:
                        log_date = datetime.strptime(timestamp, fmt)
                        break
                    except ValueError:
                        continue
                
                if not log_date:
                    print(f"DEBUG: Could not parse timestamp: {timestamp}")
                    continue

                is_match = False
                if view_type == 'daily':
                    if log_date.date() == now.date(): is_match = True
                elif view_type == 'weekly':
                    week_ago = now - timedelta(days=7)
                    if log_date >= week_ago: is_match = True
                elif view_type == 'monthly':
                    if log_date.year == now.year and log_date.month == now.month: is_match = True
                elif view_type == 'yearly':
                    if log_date.year == now.year: is_match = True
                    
                if is_match:
                    log_type = log.get('type')
                    reason = str(log.get('reason', '')).lower()
                    if log_type == 'IN' and 'refund' not in reason:
                        continue

                    item = items_by_name.get(log['item_name'])
                    if item:
                        qty = log.get('qty', 0)
                        sign = -1 if log_type == 'IN' and 'refund' in reason else 1
                        retail = item.get('retail_price', 0)
                        cost = item.get('cost_price', 0)
                        revenue = sign * qty * retail
                        profit = sign * qty * (retail - cost)
                        report_data.append({
                            "Date": log['timestamp'],
                            "Item Name": log['item_name'],
                            "Quantity": qty,
                            "Unit Price": f"P{retail:,.2f}",
                            "Total Revenue": f"P{revenue:,.2f}",
                            "Total Profit": f"P{profit:,.2f}",
                            "revenue_raw": revenue,
                            "profit_raw": profit
                        })
            except: continue

        if not report_data:
            flash(f"No data available for the selected {view_type} period.", "warning")
            return redirect(url_for('sales.sales_summary', view=view_type))

        df = pd.DataFrame(report_data)
        total_rev = sum(d['revenue_raw'] for d in report_data)
        total_prof = sum(d['profit_raw'] for d in report_data)
        
        # Final data for export (remove raw columns)
        export_df = df.drop(columns=['revenue_raw', 'profit_raw'])
        
        filename = f"Sales_Report_{view_type}_{now.strftime('%Y%m%d_%H%M%S')}"
        
        # Fetch Site Settings and User Data
        site_config = get_site_config()
        business_name = site_config.get('business_name', 'FBIHM Inventory')
        issuer_email = session.get('email', 'Unknown')
        issuer_ip = request.remote_addr or 'Unknown IP'

        from flask import current_app
        from PIL import Image
        
        # 1. Prepare Business Logo
        logo_path = None
        if site_config.get('business_logo'):
            logo_path = os.path.join(current_app.root_path, 'static', site_config.get('business_logo'))
        else:
            logo_path = os.path.join(current_app.root_path, 'static', 'images', 'login_hero.webp')
            
        png_path = "/tmp/site_logo.png"
        if os.path.exists(logo_path):
            try:
                Image.open(logo_path).convert("RGBA").save(png_path, "PNG")
            except Exception as e:
                print(f"DEBUG: Logo conversion failed: {e}")
                png_path = None
        else:
            png_path = None

        # 2. Prepare Issuer Profile Pic
        user_doc = get_users_collection().find_one({"email": issuer_email})
        profile_png = "/tmp/issuer_profile.png"
        profile_pic = None
        if user_doc and user_doc.get('profile_pic'):
            raw_pic_path = os.path.join(current_app.root_path, 'static', user_doc.get('profile_pic'))
            if os.path.exists(raw_pic_path):
                try:
                    Image.open(raw_pic_path).convert("RGBA").save(profile_png, "PNG")
                    profile_pic = profile_png
                except Exception as e:
                    print(f"DEBUG: Profile pic conversion failed: {e}")
                    profile_pic = None

        # ── Generate chart images matching the sales-summary page ────────────────
        chart_main_path = "/tmp/report_chart_main.png"
        chart_trend_path = "/tmp/report_chart_trend.png"
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.ticker as mticker
            import numpy as np

            # Build the same period-specific labels & values the frontend uses
            months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            monthly_rev  = [0.0] * 12
            monthly_prof = [0.0] * 12
            weekly_rev   = []
            weekly_profit_vals = []
            weekly_labels_list = []
            daily_rev   = []
            daily_profit_vals = []
            daily_labels_list = []

            # Using the shared parse_timestamp utility

            items_by_name2 = {item['name']: item for item in get_items_collection().find()}
            all_out_logs = list(get_inventory_log_collection().find({"type": {"$in": ["OUT", "IN"]}}))

            # Monthly
            for log in all_out_logs:
                ld = parse_timestamp(log.get('timestamp'))
                if ld and ld.year == now.year:
                    log_type = log.get('type')
                    reason = str(log.get('reason', '')).lower()
                    if log_type == 'IN' and 'refund' not in reason:
                        continue
                    item = items_by_name2.get(log['item_name'])
                    if item:
                        q = log.get('qty', 0)
                        sign = -1 if log_type == 'IN' and 'refund' in reason else 1
                        r = item.get('retail_price', 0)
                        c = item.get('cost_price', 0)
                        monthly_rev[ld.month - 1]  += sign * q * r
                        monthly_prof[ld.month - 1] += sign * q * (r - c)

            # Weekly (last 12 weeks)
            for i in range(11, -1, -1):
                start = now - timedelta(weeks=i + 1)
                end   = now - timedelta(weeks=i)
                weekly_labels_list.append(start.strftime('%-m/%-d/%y'))
                wr = wp = 0.0
                for log in all_out_logs:
                    ld = parse_timestamp(log.get('timestamp'))
                    if ld and start <= ld < end:
                        log_type = log.get('type')
                        reason = str(log.get('reason', '')).lower()
                        if log_type == 'IN' and 'refund' not in reason:
                            continue
                        item = items_by_name2.get(log['item_name'])
                        if item:
                            q = log.get('qty', 0)
                            sign = -1 if log_type == 'IN' and 'refund' in reason else 1
                            r = item.get('retail_price', 0)
                            c = item.get('cost_price', 0)
                            wr += sign * q * r; wp += sign * q * (r - c)
                weekly_rev.append(wr); weekly_profit_vals.append(wp)

            # Daily (last 30 days)
            for i in range(29, -1, -1):
                td = now - timedelta(days=i)
                daily_labels_list.append(td.strftime('%-m/%-d/%y'))
                dr = dp = 0.0
                for log in all_out_logs:
                    ld = parse_timestamp(log.get('timestamp'))
                    if ld and ld.date() == td.date():
                        log_type = log.get('type')
                        reason = str(log.get('reason', '')).lower()
                        if log_type == 'IN' and 'refund' not in reason:
                            continue
                        item = items_by_name2.get(log['item_name'])
                        if item:
                            q = log.get('qty', 0)
                            sign = -1 if log_type == 'IN' and 'refund' in reason else 1
                            r = item.get('retail_price', 0)
                            c = item.get('cost_price', 0)
                            dr += sign * q * r; dp += sign * q * (r - c)
                daily_rev.append(dr); daily_profit_vals.append(dp)

            # Choose main & trend data — same logic as the frontend
            if view_type == 'weekly':
                main_labels  = weekly_labels_list
                main_revenue = weekly_rev
                main_profit  = weekly_profit_vals
                trend_labels = weekly_labels_list
                trend_values = weekly_rev
            elif view_type == 'daily':
                main_labels  = daily_labels_list
                main_revenue = daily_rev
                main_profit  = daily_profit_vals
                trend_labels = daily_labels_list
                trend_values = daily_rev
            else:  # monthly / yearly
                main_labels  = months
                main_revenue = monthly_rev
                main_profit  = monthly_prof
                trend_labels = weekly_labels_list
                trend_values = weekly_rev

            # Chart 1 — Bar (Revenue) + Line overlay (Profit)  [matches mainChart]
            #   Colors: bars = rgba(13,110,253,0.6)/#0d6efd, line = #198754
            dark_bg = "#1a1a2e"
            fig1, ax1 = plt.subplots(figsize=(9, 3.5), facecolor=dark_bg)
            ax1.set_facecolor(dark_bg)

            x_pos = np.arange(len(main_labels))
            bars = ax1.bar(x_pos, main_revenue,
                           color='rgba(13,110,253,0.6)'.replace('rgba(13,110,253,0.6)', '#0d6efd'),
                           alpha=0.7, label='Revenue', zorder=2)
            ax1.plot(x_pos, main_profit, color='#198754', linewidth=2.5,
                     marker='o', markersize=4, label='Profit', zorder=3)

            ax1.set_title(f"{view_type.capitalize()} Revenue & Profit",
                          fontsize=12, fontweight='bold', color='white', pad=10)
            ax1.set_xticks(x_pos)
            ax1.set_xticklabels(main_labels, rotation=45, ha='right',
                                fontsize=6.5, color='#aaa')
            ax1.tick_params(axis='y', colors='#aaa', labelsize=7)
            ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"₱{v:,.0f}"))
            ax1.spines[['top', 'right', 'left', 'bottom']].set_color('#333')
            ax1.yaxis.set_tick_params(color='#333')
            ax1.set_axisbelow(True)
            ax1.yaxis.grid(True, color='#333', linewidth=0.6)
            ax1.xaxis.grid(False)
            leg1 = ax1.legend(fontsize=8, facecolor='#2a2a3e',
                              edgecolor='#333', labelcolor='white', loc='upper left')
            plt.tight_layout()
            plt.savefig(chart_main_path, dpi=140, bbox_inches='tight', facecolor=dark_bg)
            plt.close(fig1)

            # Chart 2 — Filled area line  [matches trendChart]
            #   Colors: border=#0dcaf0, fill=rgba(13,202,240,0.1)
            fig2, ax2 = plt.subplots(figsize=(5.5, 3.5), facecolor=dark_bg)
            ax2.set_facecolor(dark_bg)

            x2 = np.arange(len(trend_labels))
            ax2.fill_between(x2, trend_values, color='#0dcaf0', alpha=0.1)
            ax2.plot(x2, trend_values, color='#0dcaf0', linewidth=2,
                     marker='o', markersize=2)

            ax2.set_title("Revenue Trend", fontsize=11, fontweight='bold',
                          color='#0dcaf0', pad=10)
            ax2.set_xticks(x2)
            ax2.set_xticklabels(trend_labels, rotation=45, ha='right',
                                fontsize=5.5, color='#aaa')
            ax2.yaxis.set_visible(False)
            ax2.spines[['top', 'right', 'left', 'bottom']].set_color('#333')
            ax2.xaxis.grid(False)
            plt.tight_layout()
            plt.savefig(chart_trend_path, dpi=140, bbox_inches='tight', facecolor=dark_bg)
            plt.close(fig2)

        except Exception as e:
            chart_main_path = chart_trend_path = None
            print("DEBUG: Chart generation failed -", e)
        # ─────────────────────────────────────────────────────────────────────────


        if format_type == 'excel':
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Shift dataframe down to make room for metadata header
                export_df.to_excel(writer, index=False, sheet_name='Sales', startrow=7)
                
                # Write Summary
                summary_df = pd.DataFrame([{"Item Name": "TOTAL", "Total Revenue": f"P{total_rev:,.2f}", "Total Profit": f"P{total_prof:,.2f}"}])
                summary_df.to_excel(writer, index=False, sheet_name='Sales', startrow=len(export_df)+9)
                
                # Inject Header Metadata natively into OpenPyxl
                wb = writer.book
                ws = writer.sheets['Sales']
                ws['A1'] = business_name
                ws['A2'] = f"Report Type: {view_type.capitalize()} Sales Summary"
                ws['A3'] = f"Generated by: {issuer_email}"
                ws['A4'] = f"Issuer IP: {issuer_ip}"
                ws['A5'] = f"Timestamp: {now.strftime('%Y-%m-%d %I:%M %p')}"

                # Add Logo
                try:
                    if os.path.exists(png_path):
                        from openpyxl.drawing.image import Image as OpenPyxlImage
                        img = OpenPyxlImage(png_path)
                        img.width = 100
                        img.height = 100
                        ws.add_image(img, 'F1')
                except Exception as e: print("DEBUG: Excel logo adding failed -", e)

                # Add Profile Pic
                try:
                    if profile_pic:
                        from openpyxl.drawing.image import Image as OpenPyxlImage
                        img2 = OpenPyxlImage(profile_pic)
                        img2.width = 60
                        img2.height = 60
                        ws.add_image(img2, 'H1')
                except Exception as e: print("DEBUG: Excel profile pic adding failed -", e)

                # Charts — main bar+line & trend area (2 sheets or 1 wide sheet)
                try:
                    from openpyxl.drawing.image import Image as OpenPyxlImage
                    if chart_main_path and os.path.exists(chart_main_path):
                        chart_ws = wb.create_sheet(title='Charts')
                        img_main = OpenPyxlImage(chart_main_path)
                        img_main.width = 640; img_main.height = 250
                        chart_ws.add_image(img_main, 'A1')
                    if chart_trend_path and os.path.exists(chart_trend_path):
                        img_trend = OpenPyxlImage(chart_trend_path)
                        img_trend.width = 400; img_trend.height = 250
                        chart_ws.add_image(img_trend, 'L1')
                except Exception as e: print("DEBUG: Excel chart adding failed -", e)

            output.seek(0)
            return send_file(output, as_attachment=True, download_name=f"{filename}.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        elif format_type == 'word':
            doc = Document()
            
            # Header text
            doc.add_heading(f'{business_name} - Sales Report', 0)
            doc.add_paragraph(f'Report Type: {view_type.capitalize()} Overview')
            doc.add_paragraph(f'Generated by: {issuer_email}')
            doc.add_paragraph(f'Issuer IP: {issuer_ip}')
            doc.add_paragraph(f'Generated on: {now.strftime("%Y-%m-%d %I:%M %p")}')
            doc.add_paragraph(f'Total Revenue: P{total_rev:,.2f}')
            doc.add_paragraph(f'Total Profit: P{total_prof:,.2f}')
            
            # Images Table for side-by-side
            try:
                p = doc.add_paragraph()
                r = p.add_run()
                if png_path and os.path.exists(png_path):
                    r.add_picture(png_path, width=Inches(1.0))
                if profile_pic and os.path.exists(profile_pic):
                    r.add_text("      ") # Spacer
                    r.add_picture(profile_pic, width=Inches(0.6))
            except Exception as e: print("DEBUG: Word image adding failed -", e)
            
            table = doc.add_table(rows=1, cols=len(export_df.columns))
            table.style = 'Table Grid'
            hdr_cells = table.rows[0].cells
            for i, col in enumerate(export_df.columns):
                hdr_cells[i].text = col
                
            for _, row in export_df.iterrows():
                row_cells = table.add_row().cells
                for i, val in enumerate(row):
                    row_cells[i].text = str(val)
                    
            # Charts — main + trend side by side
            try:
                doc.add_heading('Sales Charts', level=2)
                p = doc.add_paragraph()
                r = p.add_run()
                if chart_main_path and os.path.exists(chart_main_path):
                    r.add_picture(chart_main_path, width=Inches(4.5))
                if chart_trend_path and os.path.exists(chart_trend_path):
                    r.add_text('  ')
                    r.add_picture(chart_trend_path, width=Inches(2.5))
            except Exception as e: print("DEBUG: Word chart adding failed -", e)

            output = io.BytesIO()
            doc.save(output)
            output.seek(0)
            return send_file(output, as_attachment=True, download_name=f"{filename}.docx", mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')

        else: # PDF default
            pdf = FPDF()
            pdf.add_page()
            
            # Add logos on top corners
            try:
                if png_path and os.path.exists(png_path):
                    pdf.image(png_path, x=10, y=8, w=22)
                if profile_pic and os.path.exists(profile_pic):
                    pdf.image(profile_pic, x=175, y=8, w=15)
            except Exception as e: print("DEBUG: PDF image adding failed -", e)

            # Header Info (Indented via set_x to clear the left logo
            pdf.set_y(10)
            pdf.set_x(38)
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 6, business_name, ln=True, align='L')
            
            pdf.set_x(38)
            pdf.set_font("Arial", '', 8)
            pdf.cell(0, 4, f'Report Name: {view_type.capitalize()} Sales Summary', ln=True, align='L')
            pdf.set_x(38)
            pdf.cell(0, 4, f'Generated by: {issuer_email} (IP: {issuer_ip})', ln=True, align='L')
            pdf.set_x(38)
            pdf.cell(0, 4, f'Timestamp: {now.strftime("%Y-%m-%d %I:%M %p")}', ln=True, align='L')
            
            pdf.ln(15) # Clear the header images
            
            # Summary
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(0, 8, f'Total Revenue: P{total_rev:,.2f}', ln=True)
            pdf.cell(0, 8, f'Total Profit: P{total_prof:,.2f}', ln=True)
            pdf.ln(5)
            
            # Table Header
            pdf.set_font("Arial", 'B', 8)
            cols = ["Date", "Item Name", "Qty", "Revenue", "Profit"]
            col_widths = [40, 60, 20, 35, 35]
            for i, col in enumerate(cols):
                pdf.cell(col_widths[i], 8, col, border=1, fill=False)
            pdf.ln()
            
            # Table Data
            pdf.set_font("Arial", '', 7)
            for _, row in df.iterrows():
                pdf.cell(col_widths[0], 6, str(row['Date']), border=1)
                pdf.cell(col_widths[1], 6, str(row['Item Name']), border=1)
                pdf.cell(col_widths[2], 6, str(row['Quantity']), border=1)
                pdf.cell(col_widths[3], 6, str(row['Total Revenue']), border=1)
                pdf.cell(col_widths[4], 6, str(row['Total Profit']), border=1)
                pdf.ln()
                
            # Charts page — main (left) + trend (right) on a new PDF page
            try:
                pdf.add_page()
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, f'{view_type.capitalize()} Sales Charts', ln=True, align='C')
                pdf.ln(3)
                y_start = pdf.get_y()
                if chart_main_path and os.path.exists(chart_main_path):
                    pdf.image(chart_main_path, x=8, y=y_start, w=130)
                if chart_trend_path and os.path.exists(chart_trend_path):
                    pdf.image(chart_trend_path, x=143, y=y_start, w=60)
            except Exception as e: 
                print("DEBUG: PDF chart adding failed -", e)

            output = io.BytesIO()
            pdf_content = pdf.output(dest='S')
            output.write(pdf_content)
            output.seek(0)
            return send_file(output, as_attachment=True, download_name=f"{filename}.pdf", mimetype='application/pdf')

    except Exception as e:
        import traceback
        print(f"REPORT_GEN_ERROR: {str(e)}")
        print(traceback.format_exc())
        flash(f"Error generating report: {str(e)}", "danger")
        return redirect(url_for('sales.sales_summary', view=view_type))

    # Existing return logic (Word/Excel) happens inside the format blocks
    return redirect(url_for('sales.sales_summary', view=view_type))
