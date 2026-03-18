import re

def update_sales_modal(filepath):
    try:
        with open(filepath, "r") as f:
            content = f.read()

        # We want to replace the basic select with a searchable select UI
        old_select = """                    <div class="mb-4">
                        <label class="form-label text-theme-muted small text-uppercase fw-bold ls-1">Select Item to Sell</label>
                        <select name="item_id" class="form-select bg-dark border-theme-soft text-theme-main p-3" required>
                            <option value="">-- Select --</option>
                            {% for item in items %}
                            <option value="{{ item._id }}">{{ item.name }} (Available: {{ item.stock }})</option>
                            {% endfor %}
                        </select>
                    </div>"""

        new_select = """                    <div class="mb-4">
                        <label class="form-label text-theme-muted small text-uppercase fw-bold ls-1">Select Item to Sell</label>
                        <input type="text" id="itemSearch" class="form-control bg-dark border-theme-soft text-theme-main mb-2" placeholder="Search item by name..." onkeyup="filterItemOptions()">
                        <select name="item_id" id="itemSelect" class="form-select bg-dark border-theme-soft text-theme-main p-3" size="5" required>
                            <option value="" disabled selected>-- Select an item --</option>
                            {% for item in items %}
                            <option value="{{ item._id }}">{{ item.name }} (Available: {{ item.stock }})</option>
                            {% endfor %}
                        </select>
                        <script>
                            function filterItemOptions() {
                                let input = document.getElementById('itemSearch');
                                let filter = input.value.toLowerCase();
                                let select = document.getElementById('itemSelect');
                                let options = select.getElementsByTagName('option');
                                
                                for (let i = 1; i < options.length; i++) {
                                    let txtValue = options[i].textContent || options[i].innerText;
                                    if (txtValue.toLowerCase().indexOf(filter) > -1) {
                                        options[i].style.display = "";
                                    } else {
                                        options[i].style.display = "none";
                                    }
                                }
                            }
                        </script>
                    </div>"""

        if old_select in content:
            new_content = content.replace(old_select, new_select)
            with open(filepath, "w") as f:
                f.write(new_content)
        else:
            print("Could not find the target select block in " + filepath)

    except Exception as e:
        print(f"Failed to process {filepath}: {e}")

update_sales_modal("templates/sales.html")
update_sales_modal("business-inventory-website/templates/sales.html")
