# 🕷️ fbihm team Inventory Engine v2.5.1

A high-performance, real-time inventory management system and POS ledger built with a "Hacker-Aesthetic" and enterprise-grade security features.

## 🚀 Overview
The **fbihm team Inventory Engine** is designed for modern businesses that require more than just a spreadsheet. It features real-time telemetry, a self-healing backend architecture, and a highly granular permission system.

---

## 🗺️ Website Structure & Functions

### **Site Map (Tree Diagram)**
```text
ROOT (/)
├── Public Access
│   └── /login ............................ User Authentication
│
├── Main Features (Login Required)
│   ├── /dashboard ........................ Financial Metrics & Stock Velocity
│   ├── /items ............................ Inventory Management (CRUD)
│   ├── /purchase ......................... Sales Ledger (Owner Only)
│   ├── /sales-summary .................... Visual Trends & Performance
│   ├── /restock ..................... Stock Movement Logs
│   └── /bulletin ......................... Team Task Management
│
├── Admin & Security (High Privileges)
│   ├── /admin/accounts ................... User RBAC & Permissions
│   ├── /general-setup .................... Business Profile & System Config
│   └── /system-logs ...................... Global Audit Trail
│
├── Intelligence & Diagnostics
│   ├── /ai-strategist .................... Strategic Business Insights
│   ├── /debugging-ai ..................... AI-Assisted Troubleshooting
│   ├── /developer ........................ System Stats & Watchdog Control
│   ├── /live-debug ....................... Real-time Kernel Log Stream
│   └── /health-scanner ................... Security & Link Health Scan
└── Session
    └── /logout ........................... Terminate Session
```

### **Core Backend Functions**
| Function | Description |
| :--- | :--- |
| **Metric Engine** | `calculate_item_metrics()`: Auto-computes profit, margin, revenue, and turnover rates. |
| **Audit Trail** | `log_action()`: Captures every move with proxy-aware IP tracking and timestamps. |
| **Real-time Sync** | `socketio.emit()`: Instant synchronization of data and themes across all devices. |
| **Proactive Alerts** | `send_email_notification()`: SMTP triggers for low-stock and high-value sales. |
| **Dynamic RBAC** | `get_cashier_permissions()`: Granular toggle-based access control for non-admin users. |
| **Security Guard** | `send_auth_code()`: Emailed verification codes (e.g., Code 67) for sensitive account changes. |
| **Site Safety** | `maintenance_mode_check()`: Restricts public access during system updates. |
| **Self-Healing** | `watchdog.sh`: Background daemon that auto-restarts the engine upon failure. |

---

## 🛠️ Key Features
- **Real-time Dashboard:** Financial health, turnover rates, and stock alerts.
- **Sales Velocity AI:** Algorithmic detection of "Cold Stock" and "Sporadic Sellers" to optimize inventory turnover.
- **Monthly Star Performers:** Automated identification of high-volume sales items for the current month.
- **Items Master:** Automated profit margin calculations and low-stock triggers.
- **Sales Ledger:** Comprehensive transaction history with user accountability.
- **Bulletin Board:** Collaborative task management with auto-deletion countdowns.
- **Developer Portal:** Live kernel debug streams and hardware telemetry.
- **Security:** Security Authorization Codes (e.g., Code 67) for sensitive owner modifications and strict CSP headers.
- **Communication:** Integrated VAPID Web Push and SMTP Email alerts for proactive management.
- **Recovery:** Full Backup & Restore support for JSON and CSV datasets.

## 📦 Technical Stack
- **Backend:** Python (Flask 3.x), Eventlet
- **Database:** MongoDB (NoSQL)
- **Real-time:** Flask-SocketIO (WebSockets)
- **Notifications:** Web Push (VAPID), SMTP (Email)
- **Frontend:** Bootstrap 5.3, Chart.js, Vanilla JS
- **Automation:** Bash (Self-healing Watchdog)

## 🛠️ Installation & Deployment
Refer to [DOCUMENTATION.md](DOCUMENTATION.md) for full server setup and deployment instructions.

---
*Created and Maintained by fbihm team | v2.5.1 Stable Core*
