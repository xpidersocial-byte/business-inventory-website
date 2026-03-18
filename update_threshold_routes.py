import re

with open("routes/admin.py", "r") as f:
    content = f.read()

# Remove @role_required('owner') from /settings/menu/update-ajax
# Replace:
# @admin_bp.route('/settings/menu/update-ajax', methods=['POST'])
# @login_required
# @role_required('owner')
# def update_menu_ajax():
ajax_route_old = """@admin_bp.route('/settings/menu/update-ajax', methods=['POST'])
@login_required
@role_required('owner')
def update_menu_ajax():"""

ajax_route_new = """@admin_bp.route('/settings/menu/update-ajax', methods=['POST'])
@login_required
def update_menu_ajax():"""
content = content.replace(ajax_route_old, ajax_route_new)

# Add /settings/global-thresholds/update
global_route = """@admin_bp.route('/settings/global-thresholds/update', methods=['POST'])
@login_required
def update_global_thresholds_ajax():
    data = request.get_json()
    warning = data.get('warning', 10)
    low = data.get('low', 5)
    
    get_settings_collection().update_one(
        {"type": "general"},
        {"$set": {
            "warning_threshold": int(warning),
            "low_stock_threshold": int(low)
        }},
        upsert=True
    )
    return jsonify({"success": True})

@admin_bp.route('/settings/menu/update-ajax', methods=['POST'])"""
content = content.replace("@admin_bp.route('/settings/menu/update-ajax', methods=['POST'])", global_route)

with open("routes/admin.py", "w") as f:
    f.write(content)

# Repeat for business-inventory-website/app.py
try:
    with open("business-inventory-website/app.py", "r") as f:
        content_app = f.read()
    
    app_ajax_old = """@app.route('/settings/menu/update-ajax', methods=['POST'])
@login_required
@role_required('owner')
def update_menu_ajax():"""

    app_ajax_new = """@app.route('/settings/menu/update-ajax', methods=['POST'])
@login_required
def update_menu_ajax():"""
    content_app = content_app.replace(app_ajax_old, app_ajax_new)
    
    app_global = """@app.route('/settings/global-thresholds/update', methods=['POST'])
@login_required
def update_global_thresholds_ajax():
    data = request.get_json()
    warning = data.get('warning', 10)
    low = data.get('low', 5)
    settings_collection.update_one(
        {"type": "general"},
        {"$set": {
            "warning_threshold": int(warning),
            "low_stock_threshold": int(low)
        }},
        upsert=True
    )
    return jsonify({"success": True})

@app.route('/settings/menu/update-ajax', methods=['POST'])"""
    content_app = content_app.replace("@app.route('/settings/menu/update-ajax', methods=['POST'])", app_global)
    with open("business-inventory-website/app.py", "w") as f:
        f.write(content_app)
except Exception as e:
    print(f"Skipping business-inventory-website/app.py: {e}")

