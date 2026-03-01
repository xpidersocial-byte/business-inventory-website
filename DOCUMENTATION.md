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

## 5. Deployment Process: Zero to Live Guide

Follow this exact sequence to deploy the **XPIDER Inventory Engine** on a fresh Linux Cloud Server (VPS).

### 🚀 Step 1: Get a Server
1.  **Provider:** Choose DigitalOcean, AWS, or Linode.
2.  **OS:** Select **Ubuntu 22.04 LTS** or **Debian 12**.
3.  **Specs:** Minimum 1GB RAM / 1 CPU Core.

### 🛠️ Step 2: Install System Dependencies
Once logged into your server via SSH, run:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv mongodb-server git -y
```
Ensure MongoDB is running:
```bash
sudo systemctl start mongodb
sudo systemctl enable mongodb
```

### 📦 Step 3: Clone and Setup Environment
1.  **Clone the Repo:**
    ```bash
    git clone https://github.com/xpidersocial-byte/business-inventory-website.git
    cd business-inventory-website
    ```
2.  **Create Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```
3.  **Configure Secrets:**
    Create a `.env` file and generate a strong secret key:
    ```bash
    nano .env
    ```
    Paste the following:
    ```env
    MONGO_URI=mongodb://localhost:27017/xpider_db
    SECRET_KEY=y0ur_v3ry_secr3t_k3y_h3r3
    FLASK_DEBUG=false
    ```

### ⚡ Step 4: Production Launch (The XPIDER Way)
Instead of running manually, use the **Self-Healing Watchdog** to ensure the app stays online 24/7.
```bash
chmod +x watchdog.sh
nohup ./watchdog.sh > watchdog.log 2>&1 &
```
*Your website is now running in the background.*

### 🌍 Step 5: Make it Accessible (The Funnel)
To access your website from anywhere in the world:

**Option A: Using Tailscale (Recommended for Private Business)**
1.  Install Tailscale: `curl -fsSL https://tailscale.com/install.sh | sh`
2.  Login: `sudo tailscale up`
3.  Enable Funnel: `tailscale funnel 5000`
    *This gives you a public HTTPS link immediately.*

**Option B: Using Nginx (For Public Domain)**
1.  Install Nginx: `sudo apt install nginx`
2.  Configure a reverse proxy to point to `127.0.0.1:5000`.
3.  Use **Certbot** to install a free SSL certificate for your domain.

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
