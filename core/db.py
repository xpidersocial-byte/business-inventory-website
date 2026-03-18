from extensions import mongo

def get_db():
    return mongo.db

def get_todos_collection(): return mongo.db.todos
def get_users_collection(): return mongo.db.users
def get_items_collection(): return mongo.db.items
def get_purchase_collection(): return mongo.db.purchase
def get_sales_collection(): return mongo.db.sales
def get_inventory_log_collection(): return mongo.db.inventory_log
def get_system_log_collection(): return mongo.db.system_logs
def get_categories_collection(): return mongo.db.categories
def get_notes_collection(): return mongo.db.notes
def get_subscriptions_collection(): return mongo.db.subscriptions
def get_dev_updates_collection(): return mongo.db.dev_updates
def get_menus_collection(): return mongo.db.menus
def get_settings_collection(): return mongo.db.settings
def get_undo_logs_collection(): return mongo.db.undo_logs
