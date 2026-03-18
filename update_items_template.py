import re

def remove_owner_check(filepath):
    try:
        with open(filepath, "r") as f:
            content = f.read()

        # We are looking for the "Save Changes" button in the menuSettingsBar
        # The block looks like:
        # {% if role == 'owner' %}
        # <button id="menuUpdateBtn" class="btn btn-primary btn-sm px-3 fw-bold shadow-sm" onclick="updateActiveMenuThresholds()">
        #     <i class="bi bi-check2-circle me-1"></i> Save Changes
        # </button>
        # {% endif %}

        # Use regex to find and remove the {% if role == 'owner' %} ... {% endif %} around it
        pattern = r"\{% if role == 'owner' %\}(\s*<button id=\"menuUpdateBtn\"[^>]*>.*?</button>\s*)\{% endif %\}"
        
        new_content = re.sub(pattern, r"\1", content, flags=re.DOTALL)
        
        with open(filepath, "w") as f:
            f.write(new_content)
    except Exception as e:
        print(f"Failed to process {filepath}: {e}")

remove_owner_check("templates/items.html")
remove_owner_check("business-inventory-website/templates/items.html")

