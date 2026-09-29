# IBVAP Cloud Deployment Guide (24/7 Hosting)

This guide explains how to host the **IBVAP Tactical C4I Console** on the cloud for permanent 24/7 availability so anyone in the world can access it simply by clicking a URL.

---

## Option 1: Render.com (Recommended - Free & Automated)

Render provides free cloud hosting with automated builds from GitHub.

### Step 1: Push to GitHub
1. Create a new repository on [GitHub](https://github.com/new) named `IBVAP`.
2. Run these commands in PowerShell in your project folder (`d:\IBVAP`):
   ```powershell
   git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/IBVAP.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Deploy on Render
1. Go to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repository `IBVAP`.
4. Render will automatically detect [`render.yaml`](file:///d:/IBVAP/render.yaml) or you can set:
   * **Runtime:** Python 3
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `python run_server.py`
5. Click **Create Web Service**.
6. Render will generate a permanent URL:
   `https://ibvap-tactical-console.onrender.com`

---

## Option 2: Railway.app (Instant 1-Click Container Deploy)

Railway provides continuous container deployment.

1. Go to [Railway.app](https://railway.app).
2. Click **New Project** -> **Deploy from GitHub repo**.
3. Select your `IBVAP` repo.
4. Railway will automatically build using the included [`Dockerfile`](file:///d:/IBVAP/Dockerfile).
5. In your project settings, click **Generate Domain** to get a public URL like:
   `https://ibvap-production.up.railway.app`

---

## Option 3: VPS / AWS EC2 / DigitalOcean (Docker Compose)

To host on your own Linux server or Virtual Machine:

1. Clone your repository on the server:
   ```bash
   git clone <REPO_URL>
   cd IBVAP
   ```
2. Start the container:
   ```bash
   docker compose up -d --build
   ```
3. The website will run continuously in the background on port `8000`.

---

## Pre-configured Files Included in Repository
* [`requirements.txt`](file:///d:/IBVAP/requirements.txt) - Cloud-ready dependencies (FastAPI, headless OpenCV, Uvicorn)
* [`Dockerfile`](file:///d:/IBVAP/Dockerfile) - Production Linux container definition
* [`docker-compose.yml`](file:///d:/IBVAP/docker-compose.yml) - Container orchestration
* [`render.yaml`](file:///d:/IBVAP/render.yaml) - Render blueprint configuration
* [`Procfile`](file:///d:/IBVAP/Procfile) - Cloud web process declaration
* [`run_server.py`](file:///d:/IBVAP/run_server.py) - Automatically adapts to the cloud host's dynamic `$PORT`
