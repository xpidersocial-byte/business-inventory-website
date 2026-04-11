# 🎓 Thesis Defense Cheatsheet: FBIHM Inventory Engine

This is your "Quick Reference" guide for the defense panel. Use this to find technical facts, project terminology, and key justifications in seconds.

---

## 🚀 1. The Project "DNA" (Fast Facts)
- **Official Name:** FBIHM Inventory Engine
- **Version:** 2.6.0 (Stable Core)
- **Primary Goal:** To bridge the gap between manual record-keeping and complex enterprise software for local SMEs.
- **Port:** 5000 (Internal)
- **Deployment:** Linux Server with Gitea CI/CD and Remote MongoDB Atlas Cluster.

---

## 💻 2. Technology Stack (The "How")
| Layer | Technology Used | Why? |
| :--- | :--- | :--- |
| **Backend** | **Python 3.13** | Powerful for data logic, imaging, and math. |
| **Framework** | **Flask 3.1.3** | Modular; clean separation of Auth, POS, and Admin. |
| **Database** | **MongoDB Atlas** | Cloud-native BSON storage; flexible for dynamic item types. |
| **Real-Time** | **Socket.io** | Bi-directional pipes for instant state updates. |
| **Frontend** | **Modern Vanilla JS** | Zero-dependency high speed for POS operations. |
| **UI Styling** | **CSS3 Glassmorphism**| Professional Blue-Light aesthetic (Facebook-inspired).|
| **Imaging** | **Pillow (PIL)** | Dynamic branding logic for sales reports. |

---

## 🏗️ 3. Architecture & Logic (The "Brain")
- **Standardization:** **ISO 8601** (`YYYY-MM-DDTHH:MM:SS`). Prevents data corruption and ensures global sortability of business logs.
- **Pattern:** **MVC (Model-View-Controller)**. 
- **Resilient Logic:** The `watchdog.sh` script monitors the system every **10 seconds**, auto-restarting orphaned Flask processes.
- **Sync Logic:** Centralized `parse_timestamp` utility handles cross-module date parsing safely.

---

## 🔒 4. Security Shield
- **RBAC:** Dynamic permissions matrix for Cashiers controlled by the Owner.
- **Code 67:** Security authorization code required for master account overrides.
- **Persistent State:** Notification badges are tracked server-side and cleared via Socket.io events to ensure sync across devices.

---

## 📊 5. Key Modules & "Killer" Features
1.  **Reporting Engine:** Branded PDF, Word, and Excel generation with custom business logos.
2.  **Notification Hub:** Real-time, persistent badges for low stock and system alerts.
3.  **POS Standard:** Atomic `$inc` updates and real-time inventory telemetry.
4.  **Audit Trail:** The `system_logs` and `inventory_log` provide a forensic record with IP and ISO timestamps.
5.  **Master Purge:** Complete removal of business records while preserving system settings (Owner control).

---

## 🗣️ 6. Vocabulary for the Panel (Glossary)
- **ISO 8601:** The international standard for date/time (used to ensure our data works worldwide).
- **Atomic Update:** An all-or-nothing database change (prevents stock errors if the internet blips).
- **BSON:** Binary JSON (How MongoDB stores our flexible document records).
- **Socket.io:** The "always-on" connection for instant dashboard updates.
- **CI/CD:** Continuous Integration/Deployment (Our automated Gitea workflow).

---

## 💡 7. Common "Why" Questions
- **Why ISO 8601?** "To ensure that reports are always chronologically accurate and to avoid errors caused by different regional date formats."
- **Why NoSQL?** "Retail products often have different attributes. NoSQL lets a Drink (volume) and a T-shirt (size) live in the same database without complex table joins."
- **Why Vanilla JS?** "React/Next.js are heavy. Vanilla JS provides the fastest possible response time for a busy Cashier at the POS terminal."
- **Why local server + Cloud DB?** "The local server keeps the UI fast, while the Cloud DB ensures the data is backed up and safe from hardware failure."

---
**Last Updated: 2026-04-11 | Thesis Version 2.6.0**

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
