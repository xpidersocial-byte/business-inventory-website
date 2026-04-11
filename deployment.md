# Deployment Guide: FBIHM Inventory Engine

This document provides a step-by-step guide to installing, configuring, and deploying the **FBIHM Inventory Engine** on a Linux-based server using modern CI/CD standards.

---

## 1. System Requirements

### Hardware
- **Processor:** 1.0 GHz or faster (Dual-core recommended)
- **RAM:** 2GB minimum (4GB recommended for production reporting)
- **Storage:** 10GB of free disk space (SSD preferred)

### Software
- **Operating System:** Ubuntu 22.04 LTS or any modern Linux distribution.
- **Python:** Version 3.8 to 3.13.
- **Database:** MongoDB 6.0+ (Local) or MongoDB Atlas (Recommended).
- **Imaging Libraries:** `libpng`, `libjpeg` (Required for Pillow reporting).

---

## 2. Installation Steps

### Step 1: Sync the Environment
Open your terminal and clone the repository from Gitea:
```bash
git clone https://thesis.fbihm.online/bejasadhev/FBIHM.git
cd FBIHM
```

### Step 2: Install System Dependencies
Update your package list and install the necessary Python, MongoDB, and Imaging tools:
```bash
sudo apt update
sudo apt install python3-venv python3-pip mongodb-server rsync libpng-dev libjpeg-dev -y
```

### Step 3: Set Up the Virtual Environment & Dependencies
Isolate the project's libraries and install the branding and reporting engine:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Ensure reporting tools are present
pip install Pillow matplotlib fpdf python-docx pandas
```

### Step 4: Configure Environment Variables
Create a `.env` file in the root directory:
```bash
nano .env
```
Add the following content:
```env
SECRET_KEY=your_very_secret_string
MONGO_URI=mongodb+srv://... (Your Atlas URI)
PORT=5000
FLASK_DEBUG=false
```

---

## 3. Database Initialization

Before running the app, set up the master admin and system defaults:
```bash
# Ensure local MongoDB is running if not using Atlas
sudo systemctl start mongodb

# Run the seeding scripts
python3 create_admin.py
```

---

## 4. Running the Application

### Option A: Manual Start (Development/Testing)
```bash
source venv/bin/activate
python3 app.py
```

### Option B: Using the Watchdog (Production)
The project includes a `watchdog.sh` script that automatically restarts the app if it crashes and monitors the PID.
```bash
chmod +x watchdog.sh
nohup ./watchdog.sh > watchdog.out 2>&1 &
```

---

## 5. Automation & CI/CD (Gitea Workflow)

The system is configured to sync via Gitea. To repush or update the live website:

1. **Commit changes locally:** `git add . && git commit -m "Update message"`
2. **Push to Gitea:** `git push thesis main`
3. **Remote Pull:** On the production server, pull the latest changes and restart the watchdog.

---

## 6. Business Branding Configuration
After deployment, log in as the **Owner** and visit **Profile > Settings > Business Identity**:
- Upload your **Business Logo** (used in PDF/Word reports).
- Set your **Business Name** and **Localization** settings.
- These settings are stored in Atlas and persist across server restarts.

---

## 7. Troubleshooting

- **Report Generation Error:** Ensure `Pillow` and `fpdf` are installed in the venv.
- **Date/Time Mismatch:** The system uses ISO 8601; ensure the server's system time is synced via NTP.
- **Port 5000 in use:** Run `fuser -k 5000/tcp` to clear the port.

---
**Note:** For public deployments, use **Nginx** as a reverse proxy with an SSL certificate.
