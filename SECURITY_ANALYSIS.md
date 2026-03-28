# Security & Resilience Analysis: FBIHM Inventory Engine

This document provides an evaluation of the security measures implemented to protect the **FBIHM Inventory Engine** and its users.

---

## 1. Authentication & Authorization
- **Password Hashing:** Utilizing the `Werkzeug.security` library, all user passwords are hashed using PBKDF2 with a unique salt. This prevents "plain-text" exposure in the event of a database breach.
- **Session Security:** Cookies are signed with a server-side `SECRET_KEY`. We use the `HttpOnly` flag to prevent Cross-Site Scripting (XSS) from stealing session data.
- **RBAC (Role-Based Access Control):** Granular permissions ensure that cashiers cannot access the "Net Profit" or "Delete User" functions, protecting sensitive business financial data.

## 2. Network & Frontend Security
- **Content Security Policy (CSP):** We implement a strict CSP header that restricts the sources of scripts and styles. This effectively mitigates XSS attacks by blocking unauthorized external scripts.
- **Frame Options:** The system uses `X-Frame-Options: SAMEORIGIN` to prevent "Clickjacking" attacks, ensuring the UI cannot be embedded in malicious third-party sites.
- **HTTPS Enforcement:** The system is designed to run over TLS/SSL (via Nginx or Cloudflare) to encrypt all data in transit.

## 3. Database Security
- **NoSQL Injection Prevention:** Unlike SQL databases, MongoDB is not susceptible to traditional SQL injection. By using the official `PyMongo` driver, we ensure that all queries are properly sanitized as BSON objects.
- **Connection Isolation:** The MongoDB Atlas instance is configured with IP Whitelisting, allowing only the production server to access the database.

## 4. Resilience & Availability
- **The Watchdog Daemon:** A custom self-healing script ensures that if the Flask app or MongoDB server fails, they are automatically restarted within 10 seconds.
- **PWA Offline-First (v4.0):** The Service Worker ensures that the primary UI shell and critical data (Dashboard, Items) are cached. This provides an "Offline-First" experience where the system remains populated with data even during significant network drops, using a **Stale-While-Revalidate** strategy for data consistency.
- **Global Error Handling:** Custom handlers for `ConnectionFailure` ensure that if the database is unreachable, the user is redirected to a friendly "Offline Page" instead of seeing raw stack traces.

## 5. Privacy Compliance
- **Audit Trails:** Every sensitive action (Price changes, Stock updates) is logged with the operator's email and IP address, ensuring accountability.
- **Data Minimization:** We only collect the minimum required data (Email, Name, Role) to operate the inventory system.
