# 📖 XPIDER Inventory Engine: Full Documentation

Welcome to the official documentation for the **XPIDER Inventory Engine**, a high-performance management system designed for businesses that require real-time tracking, granular control, and a modern technical interface.

---

## 1. System Architecture

### 1.1 Backend Core
- **Framework:** Flask 3.x (Python)
- **Asynchronous Layer:** Eventlet (Monkey-patched for high concurrency)
- **Real-time Sync:** Flask-SocketIO for live user telemetry and notifications.
- **Database:** MongoDB (via PyMongo) for flexible, schema-less data storage.

### 1.2 Frontend Layer
- **Layout:** Bootstrap 5.3 (Customized for dark-mode dominance)
- **Icons:** Bootstrap Icons (v1.11+)
- **Charts:** Chart.js for data visualization on the dashboard.
- **Theming:** Dynamic CSS engine supporting 15+ high-contrast presets.

---

## 2. User Roles & Access Control

The system uses a **Role-Based Access Control (RBAC)** model, further enhanced by **Dynamic Permissions**.

| Role | Standard Permissions |
| :--- | :--- |
| **Owner** | Full unrestricted access to all modules, settings, and developer tools. Can modify other accounts and wipe data. |
| **Cashier** | Typically restricted to Items Master, Sales Ledger, and Inventory IO. Specific access is toggled by the Owner. |

---

## 3. Core Modules

### 3.1 Operations Dashboard
Provides a 360-degree view of business health:
- **Financials:** Real-time Revenue, Profit, and Inventory Value.
- **Inventory Health:** Automatic "Cold Stock" (slow movers) and "Sporadic Sellers" detection.
- **Alerts:** Dynamic "Out of Stock" and "Low Stock" grids at the bottom of the page.

### 3.2 Items Master & Categories
The central repository for products:
- **Metrics:** Automatically calculates Profit Margin % and Total Revenue per item.
- **Low Stock Badges:** Visual indicators when items fall below the threshold (configurable in Setup).
- **Categories:** Dynamic categories that can be created/deleted instantly.

### 3.3 Customer Sales Ledger
A secure record of every transaction:
- **Accountability:** Tracks exactly which user (Owner/Cashier) performed each sale.
- **Stock Tracking:** Records previous vs. new stock levels for audit integrity.

### 3.4 Bulletin Board (Official)
Collaborative task tracking:
- **Priority Tags:** Mark bulletins as Urgent, Normal, or Pending.
- **Color Themes:** Choose colors for visual grouping.
- **Auto-Deletion:** Completed tasks move to a sidebar and are auto-deleted after **1 week**.

---

## 4. Administrative & Owner Tools

### 4.1 General Setup (Unified Hub)
- **Identity:** Manage Business Name, Logo Icon, and Social Links.
- **Localization:** Configure Timezone, Date, and Time formats.
- **System Logic:** Set the Maintenance Mode and Low Stock Threshold.
- **Backup:** One-click JSON export/restore for the entire database.

### 4.2 User Accounts & Permissions
- **Account Creation:** Secure modal for adding new staff.
- **Permission Matrix:** Owner-only panel to toggle every menu and setup tab for Cashier roles.
- **Security Code:** Edits to Owner accounts require the authorization code: **67**.

### 4.3 Developer Portal (Kernel Control)
- **Hardware Telemetry:** Real-time CPU, RAM, and Storage load tracking.
- **Live Debug:** Filtered stream of server logs for troubleshooting.
- **Self-Healing:** Management of the background Watchdog protocol.

---

## 5. Deployment Process

Follow these steps to deploy the **XPIDER Inventory Engine** on a fresh Linux server (Ubuntu/Debian recommended).

### 5.1 Prerequisites
- **Python 3.10+**
- **MongoDB Server** (Running locally or accessible via URI)
- **Pip & Venv** (`sudo apt install python3-pip python3-venv`)

### 5.2 Fresh Installation Steps
1. **Clone/Upload Project:**
   Place the project folder in your desired directory (e.g., `/var/www/xpider`).

2. **Initialize Environment:**
   ```bash
   cd xpider
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Create a `.env` file in the root directory:
   ```env
   MONGO_URI=mongodb://localhost:27017/xpider_db
   SECRET_KEY=your_random_secret_key_here
   FLASK_DEBUG=false
   ```

4. **Database Initialization (Optional):**
   If you have a backup, use the **Restore from JSON** feature in the Admin Settings after logging in.

### 5.3 Production Execution
For production, it is recommended to use the included **Watchdog** system to ensure 24/7 uptime.

1. **Start the Watchdog:**
   ```bash
   chmod +x watchdog.sh
   nohup ./watchdog.sh > watchdog.log 2>&1 &
   ```
   *The watchdog will automatically start the Flask app and restart it if it ever goes down.*

2. **Manual Start (For Debugging):**
   ```bash
   ./venv/bin/python3 app.py
   ```

### 5.4 Network & SSL (Tailscale/Nginx)
- **Tailscale:** The system is optimized for Tailscale Funnel. Use `tailscale funnel 5000` to expose the app securely.
- **Nginx:** If using a standard domain, configure an Nginx reverse proxy to point to `127.0.0.1:5000` and handle SSL via Certbot.

---

## 6. Maintenance & Security

### 6.1 Self-Healing Watchdog
The system includes a `watchdog.sh` script. If the Flask app crashes, the watchdog will automatically detect the failure and restart the engine within 10 seconds. This is critical for production environments.

### 6.2 Audit Trail
- **IP Logging:** Every administrative and operational action is logged with the user's IP address (X-Forwarded-For compliant for proxy support).
- **Action Logs:** Found in **Admin Settings > System Logs**, providing a permanent record of system changes.

### 6.3 Maintenance Mode
Found in **Admin Settings > General Setup**, this redirects all non-admin traffic to a secure "Under Maintenance" screen while you perform updates or data restoration.

---
*Document Version: 2.4.0 (Stabilized)*
