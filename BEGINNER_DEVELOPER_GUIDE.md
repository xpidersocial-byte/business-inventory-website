# 🚀 FBIHM Inventory Engine: Beginner Developer Guide

Welcome to the **FBIHM Inventory Engine (v2.6.0)**! This documentation is designed to help you understand how this system works, why we chose this specific professional technology stack, and how the core data standards ensure high reliability.

---

## 🛠️ The Tech Stack (The "Why" Behind the Code)

We chose these tools because they are **flexible**, **scalable**, and **standard-compliant**.

### 🐍 Flask (The Brain)
- **Why?** Flask is a "micro-framework" for Python. It provides the core logic and routing without unnecessary boilerplate.
- **Benefit:** It is the best starting point for developers who want to focus on business features rather than framework rules.

### 🎨 Blue-Light Aesthetic (The Look)
- **Why?** We moved toward a professional "Facebook-inspired" aesthetic with glassmorphism and deep blue gradients.
- **Benefit:** Provides a premium, high-density dashboard experience that is comfortable for long-term monitoring by owners and cashiers.

### 🍃 MongoDB Atlas (The Memory)
- **Why?** Traditional SQL requires rigid tables. MongoDB Atlas is a cloud-native database that grows with your item metadata.
- **Benefit:** **Hybrid Schema Logic**. If a "Toy" needs a `battery_type` field but a "Shirt" needs `fabric_type`, you can store both in the same collection without complex joins.

### 📅 ISO 8601 (The Standard)
- **Why?** Time-tracking errors can crash reporting engines.
- **Benefit:** We use `YYYY-MM-DDTHH:MM:SS` for all timestamps. This ensures the data is perfectly sortable and readable by any system globally.

### 🖼️ Pillow (The Branding Artist)
- **Why?** Reports need to look professional to build trust.
- **Benefit:** Pillow automatically handles business logo processing, ensuring that every PDF and Word document exported by the system is high-resolution and properly branded.

---

## 🌐 Infrastructure & Deployment

### 🚢 The Deployment Flow (Gitea CI/CD)
1. **Develop:** You write code on your local PC.
2. **Push:** You "Push" your code to our private Gitea remote: `thesis.fbihm.online`.
3. **Auto-Deploy:** The server detects the commit and triggers a pull, keeping the live site in sync with your latest updates.

---

## 🛡️ Reliability & The "Robot Guard" (Watchdog)

To achieve **Zero Downtime**, we use a custom script called a **Watchdog**.
- **The Task:** Runs every 10 seconds.
- **The Logic:** If the Flask web engine or the database shuts down, the Watchdog immediately restarts the process.
- **Benefit:** The store stays open even if a minor bug tries to stop the server.

---

## 💡 Quick Tips for New Contributors
- **Data Logic:** Most core logic is found in the `routes/` blueprints (Auth, Sales, Inventory, POS).
- **Branding:** To change the report logo, upload it through the Owner profile under **Business Identity**.
- **Timestamps:** Never save a date as a simple string; always use the `parse_timestamp` utility to ensure ISO 8601 compliance.
- **Theme:** UI styles are managed via CSS variables in the template headers for easy color adjustments.

*Happy coding!* 🚀
