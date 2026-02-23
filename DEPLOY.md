# CareBox Deployment Guide

## 🚀 Deploy to Render (Free Tier)

### Step 1: Encode Google Credentials

Run this in PowerShell to get your base64-encoded credentials:
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\Users\RTX\Desktop\HC\service_account.json"))
```
**Copy the output** — you'll paste it in Render.

---

### Step 2: Push Code to GitHub

```bash
cd c:\Users\RTX\Desktop\HC\carebox_project
git init
git remote add origin https://github.com/SpectralZero/HC.git
git add .
git commit -m "Initial CareBox deployment"
git branch -M main
git push -u origin main
```

---

### Step 3: Create Render Web Service

1. Go to [render.com](https://render.com) → Sign up / Log in
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repo: `SpectralZero/HC`
4. Configure:
   - **Name**: `carebox`
   - **Region**: Choose closest to Jordan (Frankfurt/EU)
   - **Branch**: `main`
   - **Root Directory**: `carebox_project`
   - **Runtime**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app -c gunicorn.conf.py`
   - **Plan**: Free

---

### Step 4: Set Environment Variables

In Render dashboard → **Environment** tab, add these:

| Variable | Value |
|----------|-------|
| `FLASK_ENV` | `production` |
| `FLASK_DEBUG` | `false` |
| `FORCE_HTTPS` | `true` |
| `FLASK_SECRET` | *(click "Generate" for a random value)* |
| `IP_HASH_SALT` | *(click "Generate" for a random value)* |
| `GOOGLE_CREDENTIALS_BASE64` | *(paste the base64 string from Step 1)* |
| `SHEETS_DOC_NAME` | `CareBoxDB` |
| `BUSINESS_WHATSAPP` | `962795246652` |
| `BUSINESS_NAME` | `CareBox` |
| `ADMIN_PASSWORD` | *(choose a strong password)* |
| `ENABLE_SERIAL_CHECK` | `true` |
| `PYTHON_VERSION` | `3.12.0` |

---

### Step 5: Deploy!

Click **"Create Web Service"** — Render will build and deploy automatically.

Your app will be live at: `https://carebox.onrender.com` (or similar)

---

## 📋 Google Sheets Setup

Your spreadsheet `CareBoxDB` needs 3 tabs with these column headers in row 1:

**BAGS tab:**
| BAG_ID | BOX_TYPE | TITLE_EN | TITLE_AR | IMAGE_URL | VIDEO_URL | TIPS_EN | TIPS_AR | PRICE | OPTIONS | SERIAL_LAST4 | IS_ACTIVE | CONTENTS |

**ORDERS tab:**
| TIMESTAMP | NAME | PHONE | BOX_TYPE | BAG_ID | NOTES | STATUS | IP_HASH |

**EVENTS tab:**
| TIMESTAMP | EVENT_TYPE | BAG_ID | BOX_TYPE | IP_HASH | USER_AGENT |

> **Important**: Share the Google Sheet with your service account email (found in `service_account.json` → `client_email` field).

---

## 🔒 Security Checklist

- [x] CSRF token protection on all forms
- [x] Honeypot fields for bot detection
- [x] IP address hashing (never stored raw)
- [x] Input sanitization against XSS
- [x] Security headers (X-Frame-Options, CSP, etc.)
- [x] Rate limiting on serial checks
- [x] Admin password authentication
- [x] HTTPS forced in production
- [x] No secrets in source code (all via env vars)
- [x] `.gitignore` excludes `.env` and `service_account.json`

---

## 🔄 Updating After Changes

```bash
cd c:\Users\RTX\Desktop\HC\carebox_project
git add .
git commit -m "Update description"
git push
```
Render auto-deploys on push to `main`.

---

## ⚠️ Free Tier Notes

- Render free tier **sleeps after 15 mins of inactivity** (first visit may take ~30s to wake)
- Google Sheets API has [quota limits](https://developers.google.com/sheets/api/limits) (300 requests/min)
- Consider upgrading to Render Starter ($7/mo) if you need always-on
