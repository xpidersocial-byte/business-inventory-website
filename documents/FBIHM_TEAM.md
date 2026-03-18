# 🕷️ fbihm team Inventory Engine: The Development Journey

This document chronicles the evolution of the **fbihm team Inventory System** from a basic To-Do prototype into a high-performance, real-time enterprise inventory management suite.

## 🌟 The Vision
The goal was to create a "Hacker-Aesthetic" inventory system that combined heavy-duty business logic (Sales, Inventory, Audit Logs) with advanced technical diagnostics (Live Kernel Streams, Web Terminal, Self-Healing Watchdogs).

## 🛠️ Technical Evolution (Process)

### Phase 1: Core Re-Architecture
- **Database:** Migrated from `mongomock` to a persistent **MongoDB** server.
- **Real-time:** Integrated **Flask-SocketIO** with **Eventlet** to support real-time online user tracking and system notifications.
- **Engine Logic:** Built a modular metric calculation engine that computes profit margins, inventory value, and turnover rates on-the-fly.

### Phase 2: Operations & Audit
- **Customer Sales Ledger:** Implemented a full ledger that tracks sales, quantity deductions, and operator accountability.
- **Inventory IO:** Created a bi-directional "Stock In/Out" system with full movement logging.
- **System Audit:** Developed a secure logging mechanism that captures **User IP Addresses**, timestamps, and granular action details.

### Phase 3: The "Kernel" (Developer Portal)
- **Live Debug:** Built a real-time log streamer that filters out noise and shows system health.
- **Self-Healing:** Created `watchdog.sh`, a background daemon that monitors the Flask process and auto-restarts the system upon failure.
- **Web Terminal:** (Decommissioned for security) Integrated a secure PTY-based browser terminal.

### Phase 4: Dynamic Permissions & Unified Admin
- **Merge Logic:** Combined "Settings" into "General Setup" to create a single administrative hub.
- **Permission Matrix:** Developed a toggle-based access system where Owners can control exactly which menus and setup tabs are visible to Cashiers.
- **Security:** Implemented a **Security Authorization Code (67)** required for modifying high-level Owner accounts.

### Phase 5: Performance Analytics & Communication (Stable)
- **Star Performers:** Automated detection of top-selling items by quantity per month.
- **Advanced Trends:** Monthly performance analysis with revenue and profit tracking.
- **Stock Velocity:** Algorithmic categorization of "Cold Stock" and "Sporadic Sellers" to optimize turnover.
- **Multi-Channel Alerts:** Integration of SMTP Email notifications and VAPID Web Push for critical stock events and sales.
- **Data Integrity:** Comprehensive Backup & Restore system supporting both JSON and CSV formats.

### Phase 6: The Next-Gen Refactor (Ongoing)
- **Architecture Shift:** Migrating from a monolithic Flask app to a modern **Next.js** frontend with a serverless backend.
- **Database Evolution:** Transitioning from MongoDB (NoSQL) to **Cloudflare D1 (SQL)** for improved edge-performance and reliability.
- **Edge Deployment:** Leveraging **Cloudflare Pages** and Workers to provide sub-millisecond latency worldwide.
- **API Modernization:** Refactoring the Python logic into TypeScript-based Edge Functions.
- **Status:** **Active Development**. The current Flask version remains the stable production baseline (v2.5.1).

## 🧬 Technical Stack (Stable / v2.5.1)
- **Languages:** Python (Flask), JavaScript (Vanilla), HTML5/CSS3 (Jinja2).
- **Database:** MongoDB (NoSQL).
- **Communication:** WebSockets (Socket.io), HTTP REST.
- **Security:** Proxy-aware IP tracking, Session Guarding, Role-based Access Control (RBAC), and CSP Headers.
- **Aesthetics:** 16+ Custom CSS Themes (Cyberpunk, Dracula, OLED, etc.) with real-time synchronization.

## 🧬 Technical Stack (Next Generation)
- **Framework:** Next.js (App Router), React, TailwindCSS.
- **Database:** Cloudflare D1 (SQLite at the Edge).
- **Deployment:** Cloudflare Pages & Workers.
- **State Management:** TanStack Query & Server Actions.

## 👨‍💻 Gemini's Role
I act as the **Lead Systems Engineer** for the fbihm team, surgically implementing modules, self-healing protocols, and ensuring high-performance reliability. My current objective is the **Next-Gen Refactor**, ensuring the project scales beyond its micro-framework origins into a world-class edge application.

---

## 🛠️ Recent Updates & Fixes (2026-03-17)

### **System Resilience & Stability**
- **Watchdog:** Optimized the self-healing daemon for faster recovery.
- **Standardization:** Harmonized project metadata and documentation to reflect the stabilized v2.5.1 core.

### **Font Loading and Theme Toggling Improvements**
-   **Font Loading:** Resolved font rendering issues by implementing a robust system font stack in `templates/base.html`, eliminating reliance on problematic external font network calls.
-   **Theme Toggling:** Corrected JSON handling for real-time theme synchronization, ensuring smooth transitions without errors.

---
*Created with Gemini CLI & fbihm team Core v2.5.1*
