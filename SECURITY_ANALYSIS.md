# Security & Resilience Analysis: FBIHM Inventory Engine

This document provides a technical evaluation of the security measures implemented to protect the **FBIHM Inventory Engine (v2.6.0)**.

---

## 1. Authentication & Authorization
- **Password Hashing:** Utilizing the `Werkzeug.security` library, all user passwords are hashed using PBKDF2 with a unique salt.
- **Session Security:** Cookies are signed with a server-side `SECRET_KEY`. We use the `HttpOnly` flag and secure cookie headers to prevent session hijacking.
- **RBAC (Role-Based Access Control):** Granular permissions ensure that cashiers cannot access "Net Profit", "System Maintenance", or "Master Purge" functions.

## 2. Network & Frontend Security
- **Content Security Policy (CSP):** We implement a strict CSP header that restricts the sources of scripts and styles, effectively mitigating XSS attacks.
- **Frame Options:** The system uses `X-Frame-Options: SAMEORIGIN` to prevent Clickjacking.
- **Gitea Integration Security:** Deployment and source control are managed via a private Gitea remote, ensuring local ownership of the codebase and preventing exposure on public repositories like GitHub.

## 3. Database Security (Atlas)
- **NoSQL Injection Prevention:** Queries are sanitized as BSON objects via the official `PyMongo` driver.
- **Connection Isolation:** The MongoDB Atlas instance is configured with TLS encryption for data in transit and IP Whitelisting for all remote access.
- **Data Maintenance:** A "Master Purge" utility exists for surgical data removal, requiring Owner authorization to ensure data privacy during handover.

## 4. Resilience & Availability
- **The Watchdog Daemon:** A custom self-healing script ensures that if the Flask app or MongoDB server fails, they are automatically restarted within 10 seconds.
- **ISO 8601 Data Standard:** By enforcing the `YYYY-MM-DDTHH:MM:SS` format, we eliminate application "panics" and crashes previously caused by malformed date strings in legacy records.
- **PWA Persistence:** The Service Worker ensures that the primary UI and critical dashboard telemetry remain accessible during network drops.

## 5. Privacy Compliance & Auditing
- **Standardized Audit Trails:** Every price change or stock update is logged with an **ISO 8601 Timestamp**, the operator's email, and their IP address. This creates a tamper-evident chronological record.
- **Data Cleansing:** The maintenance module allows the owner to purge all business history (sales and summary data) while preserving system configuration and user accounts.

---
**Last Updated: 2026-04-11 | Version 2.6.0 Security Audit**
