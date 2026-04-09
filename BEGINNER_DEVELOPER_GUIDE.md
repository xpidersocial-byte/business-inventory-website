# 🚀 FBIHM Inventory Engine: Beginner Developer Guide

Welcome to the **FBIHM Inventory Engine**! This documentation is designed to help you understand how this website works, why we chose this specific technology stack, and how the entire system stays alive and reliable.

---

## 🛠️ The Tech Stack (The "Why" Behind the Code)

We chose these tools because they are **flexible**, **scalable**, and **beginner-friendly**. You don't need to be a senior engineer to modify this website!

### 🐍 Flask (The Brain)
- **Why?** Flask is a "micro-framework" for Python. Unlike larger frameworks (like Django), Flask stays out of your way.
- **Benefit:** It is the best starting point for beginners. You can modify the website exactly how you want with minimal rules.
- **Docs:** [Flask Documentation](https://flask.palletsprojects.com/en/stable/)

### 🎨 Bootstrap 5 (The Look)
- **Why?** Designing CSS from scratch is time-consuming. Bootstrap gives you pre-made "building blocks."
- **Benefit:** No need to write complex CSS. Want a card? Use a `<div class="card">`. Want a responsive container? Use `.container`. It handles everything automatically.
- **Docs:** [Bootstrap Getting Started](https://getbootstrap.com/docs/5.3/getting-started/introduction/)

### 🍃 MongoDB (The Memory)
- **Why?** Traditional databases (SQL) require strict tables. If you want to add a `middle_name` field, you have to run a scary `ALTER TABLE` command that might break things.
- **Benefit:** MongoDB is **stress-free**. If you need to save a new field, you just... start saving it. It's like a digital filing cabinet that grows with you.
- **Docs:** [MongoDB Documentation](https://www.mongodb.com/docs/)

### 📶 PouchDB (The "Offline" Secret)
- **Why?** What happens if the internet goes down while you're selling a product?
- **Benefit:** We use a **PWA (Progressive Web App)** approach. PouchDB acts as a "mini-database" inside your browser. It saves your work locally, then automatically syncs it back to the server when the internet returns.
- **Docs:** [Going Offline with PWAs](https://developers.google.com/codelabs/pwa-training/pwa03--going-offline)

### 📊 Chart.js (The Eyes)
- **Why?** Numbers are boring; graphs are better.
- **Benefit:** Chart.js takes your sales data and turns it into beautiful, interactive charts effortlessly.
- **Docs:** [Chart.js Documentation](https://www.chartjs.org/)

---

## 🌐 Infrastructure & Deployment

This website doesn't just live on a laptop; it's a professional-grade deployment.

| Component | Provider / Tool | URL |
| :--- | :--- | :--- |
| **Server** | IONOS | `74.208.174.70` |
| **Management**| Portainer | (Server GUI for Docker) |

### 🚢 The Deployment Flow
1. **Develop:** You write code on your PC.
2. **Push:** You "Push" your code to the server.
3. **Auto-Deploy:** The server uses an automated **Workflow**. It detects the new code, logs into the system, and replaces the old website files with your fresh update instantly.

---

## 🛡️ Reliability & The "Robot Guard" (Watchdog)

One common problem: **Deployments can sometimes shut down a server briefly.** 

### The Solution: `watchdog.sh`
To achieve **Zero Downtime**, we use a custom script called a **Watchdog**.
- **The Task:** It runs in the background every 10 seconds.
- **The Logic:** If it detects that the website (Flask) or the database (MongoDB) has stopped, it **immediately restarts them**. 
- **Benefit:** Your website stays alive even if a deployment or a bug tries to shut it down.

> [!TIP]
> This is based on professional best practices. You can read more about this type of "process monitoring" here: [Watchdog Gist Documentation](https://gist.github.com/vodolaz095/5073080).

---

## 🐳 Server-Side Containers
We use **Docker** to keep everything organized. Instead of installing a mess of tools on the server, we use "Containers":
- **MongoDB Container:** Keeps your data isolated and safe.
- **Gitea Container:** Manages your code history (like a private GitHub).

---

## 💡 Quick Tips for Beginners
- **Modify anything:** Because it's Flask, you can find most logic in `app.py` or the `routes/` folder.
- **Change the design:** Go to the `templates/` folder and use Bootstrap classes to change how pages look.
- **Keep it simple:** You don't need a PhD to run this. Just write Python, use Bootstrap tags, and let the **Watchdog** handle the rest!

*Happy coding!* 🚀
