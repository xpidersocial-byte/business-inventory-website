# fbihm team Inventory Engine: System Summary & Process Map

## 🚀 Overview
The fbihm team Inventory Engine (v2.5.1) is a high-performance, real-time inventory management and POS system. It is built using a modern technical stack featuring Flask, MongoDB, and WebSockets (Socket.io), designed with a "Hacker-Aesthetic" and enterprise-grade security.

---

## 🗺️ System Process Map (Mermaid)

```mermaid
graph TD
    A[User Access] --> B[Flask Web Server (app.py)]
    B --> C[Role-Based Access Control]
    B <--> D[Socket.io WebSockets]
    D --> E[Connected Users & Dashboards]
    B --> F[MongoDB]
    F --> G[Sales, Items, System Logs, Settings]
    B --> H[Background Watchdog]
    H --> I[Auto-Recovery / Restart]
    B --> J[Notifications / Alerts]
```

---

## 🌐 How the System Works: A 6-Step Breakdown
The fbihm team Inventory Engine operates through a layered architecture designed for high speed and reliability.

1. The Entry Point (User Access)
   * Authentication: The Flask Web Server (`app.py`) uses decorators to ensure only authorized users access the system.
   * Dynamic RBAC: Once logged in, the Role-Based Access Control checks if you are an Owner or Cashier. Owners can dynamically toggle menu visibility for Cashiers through a custom permission matrix.
2. The "Heartbeat" (Real-time Sync)
   * WebSockets: The system uses Socket.io for bi-directional communication.
   * Instant Telemetry: When a sale is made on one device, the server emits a signal that updates the dashboards and stock levels of all other connected users instantly—no page refresh required.
3. The Data Engine (MongoDB)
   * Flexible Documents: Every product and sale is stored as a JSON-like document in MongoDB.
   * Automated Logic: The engine automatically calculates profit, margins, and revenue for every item during a sale, updating the database in real-time.
4. The Security Guard (Code 67)
   * Critical Override: Sensitive modifications (like changing Owner account details) require a specialized Security Authorization Code (67). This provides an additional layer of protection against unauthorized local access.
5. The Self-Healing Brain (Watchdog)
   * 24/7 Supervision: A background Bash Watchdog Daemon monitors the Flask and MongoDB processes every 10 seconds.
   * Auto-Recovery: If any core service crashes, the watchdog identifies the failure and restarts the engine automatically within seconds.
6. Proactive Alerts
   * Notification Hub: The system monitors inventory thresholds and instantly "pushes" alerts to the Owner via SMTP (Email) and VAPID (Web Push) when stock reaches critical levels.

---

## 🤖 Automation & Self-Healing
The system is designed for Zero-Intervention Operations, using background daemons and automated logic to maintain 24/7 uptime and data integrity.

1. Self-Healing Watchdog (`watchdog.sh`)
   * Continuous Monitoring: A background Bash daemon polls the system every 10 seconds.
   * Auto-Recovery:
     * MongoDB: If the database service crashes, the watchdog auto-forks a new mongod instance.
     * Flask Engine: If the web server dies, the watchdog triggers a nohup restart immediately.
2. Automated Health Scanner (`scanner.py`)
   * Crawler Logic: Systematically traverses the internal site structure (up to 50 pages).
   * Broken Link Detection: Automatically identifies 404 errors and 500 server errors across all routes.
   * Security Audit: Proactively checks for missing headers and probes for exposed sensitive files.

---

## 🎓 Educational Advantages: Why this Stack for Students?
The fbihm team Inventory Engine is an ideal learning platform for students exploring full-stack engineering.

1. Python & Flask (The "Micro" Advantage)
   * Readability: Python's clean syntax allows students to focus on logic rather than boilerplate.
   * Fundamentals: Flask is a "micro-framework" that teaches the core principles of HTTP, routing, and middleware.
2. MongoDB (Schema Flexibility)
   * NoSQL Learning: Students can explore data relationships without the steep learning curve of complex SQL joins.
   * JSON-Native: Seamless data flow between the frontend (JS) and backend (Python).
3. Real-World Patterns
   * WebSockets: Teaches real-time bi-directional communication.
   * Reliability: Introduces concepts of system monitoring and process auto-recovery.

---

## 🛠️ Technical Components
1. Backend Layer (Flask 3.x)
   * Eventlet: Monkey-patched for high concurrency and async execution.
   * Socket.io: Powers real-time telemetry and instant synchronization.
2. Storage Layer (MongoDB)
   * Collections: users, items, sales, system_logs, categories, notes, subscriptions, settings.

---

## 🔑 Security & Guardrails
* Code 67: A specialized security authorization code for critical account changes.
* Audit Integrity: Proxy-aware IP address tracking for every system modification.
* Maintenance Mode: Owner-controlled lock for updates and data restoration.

---

Created on 2026-03-12 | fbihm team Technical Documentation
