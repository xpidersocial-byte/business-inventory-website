from functools import wraps
from flask import session, redirect, url_for, request, flash
from core.db import get_settings_collection

def get_cashier_permissions():
    settings_collection = get_settings_collection()
    perms = settings_collection.find_one({"type": "cashier_permissions"})
    if not perms:
        # Default: Cashiers only see basic sales/inventory
        perms = {
            "type": "cashier_permissions",
            "dashboard": True,
            "items_master": True,
            "sales_ledger": True,
            "sales_summary": False,
            "restock": True,
            "bulletin_board": True,
            "developer_portal": False,
            "live_debug": False,
            "health_scanner": False,
            "admin_accounts": False,
            "general_setup": False,
            "system_logs": False,
            "setup_identity": False,
            "setup_localization": False,
            "setup_logic": False,
            "setup_categories": True,
            "setup_advanced": False,
            "setup_assets": False,
            "setup_backup": False,
            "setup_danger_zone": False,
            "setup_smtp": False,
            "setup_notifications": False
        }
        settings_collection.insert_one(perms)
    return perms

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            return redirect(url_for('auth.index'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'email' not in session:
                return redirect(url_for('auth.index'))
            
            user_role = session.get('role', 'cashier')
            if user_role == 'owner':
                return f(*args, **kwargs) # Owners always allowed
            
            # For cashiers, check dynamic permissions
            perms = get_cashier_permissions()
            endpoint = request.endpoint
            
            # Map endpoints to permission keys
            mapping = {
                'dashboard.dashboard': 'dashboard',
                'inventory.items': 'items_master',
                'sales.sales_list': 'sales_ledger',
                'sales.sales_summary': 'sales_summary',
                'inventory.restock': 'restock',
                'developer.developer_portal': 'developer_portal',
                'developer.live_debug': 'live_debug',
                'developer.health_scanner': 'health_scanner',
                'admin.admin_accounts': 'admin_accounts',
                'admin.general_setup': 'general_setup',
                'admin.system_logs': 'system_logs'
            }
            
            perm_key = mapping.get(endpoint)
            if perm_key and not perms.get(perm_key, False):
                flash("Access Denied: The administrator has restricted this feature.", "danger")
                return redirect(url_for('dashboard.dashboard'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator
