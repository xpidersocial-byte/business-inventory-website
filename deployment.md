# Deployment Guide: FBIHM Inventory Engine

This document provides a step-by-step guide to installing, configuring, and deploying the FBIHM Inventory Engine on a Linux-based server.

---

## 1. System Requirements

### Hardware
- **Processor:** 1.0 GHz or faster (Dual-core recommended)
- **RAM:** 2GB minimum (4GB recommended for production)
- **Storage:** 10GB of free disk space (SSD preferred)

### Software
- **Operating System:** Ubuntu 22.04 LTS or any modern Linux distribution.
- **Python:** Version 3.8 to 3.12.
- **Database:** MongoDB 6.0 or higher.
- **Web Browser:** Chrome, Firefox, or Safari (for the client-side).

---

## 2. Installation Steps

### Step 1: Clone the Repository
Open your terminal and download the source code:
```bash
git clone https://github.com/your-username/fbihm-inventory.git
cd fbihm-inventory
```

### Step 2: Install System Dependencies
Update your package list and install the necessary Python and MongoDB tools:
```bash
sudo apt update
sudo apt install python3-venv python3-pip mongodb-server rsync -y
```

### Step 3: Set Up the Virtual Environment
Isolate the project's libraries to prevent conflicts with other apps:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Create a `.env` file in the root directory to store your secret keys and database connection:
```bash
nano .env
```
Add the following content (update with your actual data):
```env
SECRET_KEY=your_very_secret_string
MONGO_URI=mongodb://localhost:27017/fbihm_db
PORT=5000
FLASK_DEBUG=false
```

---

## 3. Database Initialization

Before running the app, you need to set up the admin account and initial items:
```bash
# Ensure MongoDB is running
sudo systemctl start mongodb

# Run the seeding scripts
python3 create_admin.py
python3 initial_data.py
```

---

## 4. Running the Application

### Option A: Manual Start (For Testing)
```bash
source venv/bin/activate
python3 app.py
```
The app will be available at `http://localhost:5000`.

### Option B: Using the Watchdog (Recommended for 24/7 Uptime)
The project includes a `watchdog.sh` script that automatically restarts the app if it crashes.
```bash
chmod +x watchdog.sh
./watchdog.sh &
```

---

## 5. Automation & CI/CD (GitHub Actions)

If you want the server to update automatically every time you push code to GitHub:

1.  **Set up a GitHub Runner:** Go to your GitHub Repo -> Settings -> Actions -> Runners -> New self-hosted runner.
2.  **Follow the GitHub instructions** to install the runner on your server.
3.  **Deploy:** Once the runner is active, any push to the `main` branch will trigger the `.github/workflows/deploy.yml` file, which will:
    - Sync the latest code.
    - Re-install any new libraries.
    - Restart the Flask server.

---

## 6. Troubleshooting

- **Port 5000 already in use:** Run `fuser -k 5000/tcp` to clear the port.
- **Database Connection Error:** Check if MongoDB is active using `sudo systemctl status mongodb`.
- **Permission Denied:** Ensure you have granted execute permissions to the scripts using `chmod +x <filename>`.

---
**Note:** For public deployments (online), it is highly recommended to use a reverse proxy like **Nginx** and an SSL certificate from **Let's Encrypt** to secure the connection.
