import re

def fix_permissions(filepath, old_text, new_text):
    try:
        with open(filepath, "r") as f:
            content = f.read()

        new_content = content.replace(old_text, new_text)
        
        with open(filepath, "w") as f:
            f.write(new_content)
    except Exception as e:
        print(f"Failed to process {filepath}: {e}")

fix_permissions("core/middleware.py", "'inventory.restock': 'inventory_io',", "'inventory.restock': 'restock',")
fix_permissions("business-inventory-website/app.py", "'restock': 'inventory_io',", "'restock': 'restock',")
fix_permissions("templates/base.html", "cashier_perms.inventory_io", "cashier_perms.restock")
fix_permissions("business-inventory-website/templates/base.html", "cashier_perms.inventory_io", "cashier_perms.restock")

