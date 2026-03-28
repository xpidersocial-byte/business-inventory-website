# 🎓 Thesis Defense Cheatsheet: FBIHM Inventory Engine

This is your "Quick Reference" guide for the defense panel. Use this to find technical facts, project terminology, and key justifications in seconds.

---

## 🚀 1. The Project "DNA" (Fast Facts)
- **Official Name:** FBIHM Inventory Engine
- **Version:** 2.5.1 (Stable Core)
- **Primary Goal:** To bridge the gap between manual record-keeping and complex enterprise software for local SMEs.
- **Port:** 5000 (Internal)
- **Deployment:** Local Linux Server with Cloud-Synchronized Database (MongoDB Atlas).

---

## 💻 2. Technology Stack (The "How")
| Layer | Technology Used | Why? |
| :--- | :--- | :--- |
| **Backend** | **Python 3.13** | Powerful for data logic and math. |
| **Framework** | **Flask 3.1.3** | Micro-framework; lightweight and modular. |
| **Database** | **MongoDB (NoSQL)** | Flexible; handles diverse item categories easily. |
| **Real-Time** | **Socket.io** | Instant updates across all connected screens. |
| **Frontend** | **Vanilla JS (ES6+)** | Fast browser performance without heavy frameworks. |
| **UI Styling** | **Bootstrap 5.3** | Responsive design; works on tablets and desktops. |
| **Server Engine** | **Eventlet** | Handles high-concurrency (multiple POS terminals). |

---

## 🏗️ 3. Architecture & Logic (The "Brain")
- **Pattern:** **MVC (Model-View-Controller)**. 
    - *Model:* MongoDB documents. 
    - *View:* Jinja2 HTML templates. 
    - *Controller:* Flask Blueprints (`auth`, `pos`, `sales`, `inventory`).
- **PWA (Progressive Web App):** Uses a **Service Worker** (`sw.js`) to cache the store UI, enabling basic navigation even if the server blips.
- **Self-Healing:** The `watchdog.sh` script polls the system every **10 seconds** to ensure the database and server are always running.

---

## 🔒 4. Security Shield
- **RBAC (Role-Based Access Control):** 
    - **Owner:** Full access (Profits, User Management).
    - **Cashier:** Restricted access (POS, Items, Bulletin).
- **Password Protection:** PBKDF2 hashing with salt (never stored in plain text).
- **Code 67:** A mandatory authorization code required for sensitive "Owner" modifications to prevent unauthorized local overrides.
- **CSP (Content Security Policy):** Blocks external scripts from running on the website, preventing XSS attacks.

---

## 📊 5. Key Modules & "Killer" Features
1.  **POS Module:** Real-time stock validation and PDF receipt generation.
2.  **Star Performers:** Algorithmic detection of top-selling items per month.
3.  **Dormant Stock:** Identifies items with zero sales in 30+ days.
4.  **Low Stock Alerts:** Automatic email notifications via SMTP when stock hits a user-defined threshold.
5.  **Audit Trail:** The `inventory_log` records every single "IN" and "OUT" with a timestamp and user ID.

---

## 🗣️ 6. Vocabulary for the Panel (Glossary)
- **CRUD:** Create, Read, Update, Delete (The basic functions of our inventory).
- **BSON:** Binary JSON (How MongoDB stores our data).
- **WebSocket:** The "open pipe" that SocketIO uses for instant communication.
- **Race Condition:** When two users buy the last item at once (We prevent this with atomic `$inc` updates).
- **CI/CD:** Continuous Integration/Deployment (How our GitHub Actions automatically update the server).
- **Atomic Operation:** A database update that happens all at once or not at all (preventing partial data loss).
- **Offline-First (PWA):** A strategy where the app prioritizes loading from the local cache, allowing the system to remain functional (viewable) without a live internet connection.

---

## 💡 7. Common "Why" Questions
- **Why NoSQL?** "Because retail items are irregular. A Car has a model year; a Drink has a volume. NoSQL lets them coexist in one collection."
- **Why not Next.js?** "We prioritized backend data processing and low-resource reliability over frontend complexity."
- **Why not SQL?** "SQL requires rigid schemas. Small businesses change their product types frequently; NoSQL adapts to them instantly."
- **Why local server?** "To ensure the POS works at full speed even if the public internet is slow."

---
**PRO-TIP:** If they ask about something you haven't built yet, say: *"That is currently in our **Future Roadmap**, which includes migrating to a serverless Edge architecture using Next.js and D1."*
