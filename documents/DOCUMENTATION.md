# 📖 fbihm team Inventory Engine: Full Documentation

Welcome to the official documentation for the **fbihm team Inventory Engine (v2.5.1)**. This system is designed for high-performance inventory management, real-time POS operations, and secure business oversight.

---

## 1. System Architecture

### 1.1 Backend Core
- **Framework:** Flask 3.1.3 (Python)
- **Asynchronous Layer:** Eventlet (Monkey-patched)
- **Real-time Sync:** Flask-SocketIO for live data telemetry.
- **Database:** MongoDB (PyMongo) for schema-less storage.
- **Security:** CSP headers, RBAC, and Security Authorization Codes.

### 1.2 Frontend Layer
- **Layout:** Bootstrap 5.3 (Dark-mode optimized)
- **Icons:** Bootstrap Icons (v1.11+)
- **Charts:** Chart.js for visualization.
- **Theming:** 16+ custom high-contrast CSS presets with real-time sync.

---

## 2. User Roles & Access Control

The system uses a **Role-Based Access Control (RBAC)** model with **Dynamic Permission Matrix**.

| Role | Access Level |
| :--- | :--- |
| **Owner** | Full unrestricted access. Can toggle visibility for Cashiers. |
| **Cashier** | Restricted access based on Owner-defined permissions. |

---

## 3. Core Modules

### 3.1 Operations Dashboard
- **Financial Metrics:** Revenue, Profit, and Inventory Value tracking.
- **Stock Velocity:** Algorithmic detection of "Cold Stock" and "Sporadic Sellers".
- **Real-time Grids:** Instant updates for stock levels and transactions.

### 3.2 Items Master & Categories
- **Profit Margin %:** Auto-calculated per item based on actual sales.
- **Low Stock Triggers:** Visual and proactive alerts for replenishment.
- **Dynamic Categories:** Instant creation/deletion with CSV restoration support.

### 3.3 Customer Sales Ledger
- **Transaction History:** Detailed record of every sale with operator tracking.
- **Audit Logs:** Previous vs. current stock levels for integrity verification.

### 3.4 XPIDER AI Engine (Beta)
- **Business Insights:** Strategic bullets based on current inventory data.
- **Diagnostic Assistant:** Site-wide health scans and error analysis.
- *Note: AI functionality is currently in a placeholder/development state during the Next.js migration.*

---

## 4. Administrative & Owner Tools

### 4.1 General Setup
- **Identity:** Manage Business Name, Logo, and Socials.
- **Localization:** Configure Timezone and Date formats.
- **Maintenance:** Toggle global maintenance mode.

### 4.2 Security Code (67)
Critical modifications to Owner accounts require the specialized authorization code: **67**. This is a mandatory guard against unauthorized local modifications.

### 4.3 Developer Portal
- **Hardware Telemetry:** Live CPU, RAM, and Storage load monitoring.
- **Live Debug:** Real-time stream of server logs via SocketIO.
- **Self-Healing:** Management of the background `watchdog.sh` process.

---

## 5. Deployment Guide (Flask Baseline)

### 🚀 Step 1: System Dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv mongodb-server git -y
```

### 🛠️ Step 2: Environment Setup
1.  **Clone:** `git clone https://github.com/fbihmteam/business-inventory-website.git`
2.  **Venv:** `python3 -m venv venv && source venv/bin/activate`
3.  **Install:** `pip install -r requirements.txt`

### ⚡ Step 3: Production Launch
```bash
chmod +x watchdog.sh
nohup ./watchdog.sh > watchdog.log 2>&1 &
```

---

## 6. Next-Gen Migration (Future Roadmap)

We are currently refactoring the engine to leverage modern Edge technologies:
- **Frontend:** Next.js (App Router) + TailwindCSS.
- **Database:** Cloudflare D1 (SQLite) for ultra-low latency.
- **Hosting:** Cloudflare Pages & Workers.
- **Timeline:** Migration is ongoing; Flask remains the stable production baseline.

---
*Last Updated: 2026-03-17 | v2.5.1 Stabilized*
