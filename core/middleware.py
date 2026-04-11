from functools import wraps
from flask import session, redirect, url_for, request, flash
from core.db import get_settings_collection

def get_cashier_permissions():
    settings_collection = get_settings_collection()
    perms = settings_collection.find_one({"type": "cashier_permissions"})
    if not perms:
        perms = {
            "type": "cashier_permissions",
            "dashboard": True, "pos": True, "items_master": True, "sales_ledger": True,
            "sales_summary": False, "restock": True, "bulletin_board": True, "legend": True,
            "developer_portal": False, "live_debug": False, "health_scanner": False,
            "admin_accounts": False, "general_setup": False, "system_logs": False,
            "setup_identity": False, "setup_localization": False, "setup_logic": False,
            "setup_categories": True, "setup_advanced": False, "setup_assets": False,
            "setup_backup": False, "setup_danger_zone": False, "setup_smtp": False,
            "setup_notifications": False
        }
        settings_collection.insert_one(perms)
    return perms

def get_owner_permissions():
    settings_collection = get_settings_collection()
    perms = settings_collection.find_one({"type": "owner_permissions"})
    if not perms:
        # Owners default to everything True
        perms = {
            "type": "owner_permissions",
            "dashboard": True, "pos": True, "items_master": True, "sales_ledger": True,
            "sales_summary": True, "restock": True, "bulletin_board": True, "legend": True,
            "developer_portal": True, "live_debug": True, "health_scanner": True,
            "admin_accounts": True, "general_setup": True, "system_logs": True,
            "setup_identity": True, "setup_localization": True, "setup_logic": True,
            "setup_categories": True, "setup_themes": True, "setup_advanced": True,
            "setup_assets": True, "setup_backup": True, "setup_danger_zone": True,
            "setup_smtp": True, "setup_notifications": True
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
            user_email = session.get('email')
            endpoint = request.endpoint
            
            # Map endpoints to permission keys
            mapping = {
                'dashboard.dashboard': 'dashboard',
                'pos.pos_view': 'pos',
                'inventory.items': 'items_master',
                'sales.sales_list': 'sales_ledger',
                'sales.sales_summary': 'sales_summary',
                'inventory.restock': 'restock',
                'developer.developer_portal': 'developer_portal',
                'developer.live_debug': 'live_debug',
                'developer.health_scanner': 'health_scanner',
                'admin.admin_accounts': 'admin_accounts',
                'admin.general_setup': 'general_setup',
                'admin.system_logs': 'system_logs',
                'bulletin.bulletin': 'bulletin_board',
                'inventory.legend': 'legend'
            }
            
            perm_key = mapping.get(endpoint)

            # Super Admin Fail-safe: admin@inventory.com can ALWAYS access critical management pages
            if user_email == 'admin@inventory.com' and perm_key in ['admin_accounts', 'general_setup']:
                return f(*args, **kwargs)
            
            # Get permissions based on role
            if user_role == 'owner':
                perms = get_owner_permissions()
            else:
                perms = get_cashier_permissions()
            
            # 1. First check if the feature is globally disabled for the user's role
            if perm_key and not perms.get(perm_key, True):
                flash(f"Access Denied: The {user_role} access for this feature is currently disabled.", "warning")
                return redirect(url_for('dashboard.dashboard'))

            # 2. Check if the user has the required role for the endpoint (if not owner)
            if user_role == 'owner':
                return f(*args, **kwargs)
            
            # If cashier, they only get here if the permission was True in cashier_perms
            if role == 'owner' and user_role != 'owner':
                flash("Access Denied: This area requires Owner privileges.", "danger")
                return redirect(url_for('dashboard.dashboard'))
                
            return f(*args, **kwargs)
            
        return decorated_function
    return decorator
