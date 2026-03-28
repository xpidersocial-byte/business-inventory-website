# System Design & Architecture: FBIHM Inventory Engine

This document provides a technical blueprint of the **FBIHM Inventory Engine**, explaining how the different components interact.

---

## 1. High-Level Architecture
The system follows a **Monolithic Modular Architecture** built on the **Model-View-Controller (MVC)** pattern.

- **Model:** MongoDB Collections (Data storage).
- **View:** HTML Templates rendered via Jinja2 (User interface).
- **Controller:** Flask Routes and Blueprints (Business logic).

---

## 2. Data Flow Diagram (DFD)
1.  **Input:** A cashier clicks "Sell" on the POS screen.
2.  **Processing:** 
    - The Frontend (JS) sends a JSON payload to `/pos/checkout`.
    - The Backend (Flask) validates the stock in MongoDB.
    - If valid, the Backend deducts stock using `$inc`.
    - A record is added to the `purchase` and `inventory_log` collections.
3.  **Real-time Update:** 
    - The server emits a `dashboard_update` event via SocketIO.
    - All connected clients refresh their charts and badges instantly.
4.  **Output:** A PDF receipt is generated, and an email alert is sent if stock is low.

---

## 3. Database Schema (NoSQL)
The system uses **MongoDB**, which stores data in flexible BSON documents.

### Key Collections:
- **`users`:** Stores login credentials, roles (Owner/Cashier), and profile preferences.
- **`items`:** Central inventory repository (name, cost, retail, current stock, category).
- **`purchase`:** Transaction history (linked to items and user emails).
- **`inventory_log`:** Audit trail for every stock movement ("IN" or "OUT").
- **`settings`:** Global system configuration (Business name, thresholds, SMTP).

---

## 4. Frontend Components
- **Dashboard:** Uses **Chart.js** to render data visualization layers.
- **POS Screen:** A single-page interface managed by vanilla JavaScript for fast cart interactions.
- **Service Worker (`sw.js`):** Manages the PWA cache for offline availability.

---

## 5. Backend Service Modules
- **Metric Engine:** A specialized module (`calculate_item_metrics`) that computes profit margins and stock status on-the-fly.
- **Communication Layer:** Handles SMTP (Email) and VAPID (Web Push) protocols.
- **Security Layer:** Implements RBAC checks and CSP header injection.

---

## 6. Self-Healing Mechanism
- **The Watchdog:** A background bash script that monitors the `PID` of the Flask app and MongoDB. If a process stops, the script auto-restarts it to maintain 99.9% uptime.
