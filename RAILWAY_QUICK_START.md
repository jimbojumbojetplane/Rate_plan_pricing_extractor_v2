# Railway Quick Start Guide

## 🚀 Deploy in 5 Minutes

### Step 1: Sign Up
1. Go to https://railway.app
2. Click "Start a New Project"
3. Sign in with GitHub

### Step 2: Connect Repository
1. Click "Deploy from GitHub repo"
2. Select: `Rate_plan_pricing_extractor_v2`
3. Click "Deploy Now"

### Step 3: Wait for Deployment
- Railway will automatically:
  - Detect Python project
  - Install dependencies from `requirements.txt`
  - Start Streamlit using `Procfile`
  - Generate a public URL

### Step 4: Get Your URL
- Once deployed, Railway shows your app URL
- Example: `https://your-app-name.up.railway.app`
- Click the URL to open your dashboard

## ✅ That's It!

Your dashboard is now live 24/7. Every time you push a new consolidated file to GitHub, Railway will automatically redeploy with the latest data.

## 💰 Pricing

- **Free Trial**: $5 credit (good for ~1 month)
- **Hobby Plan**: $5/month (recommended for this dashboard)
- **Pro Plan**: $20/month (if you need more resources)

## 📝 Important Files

These files are already configured:
- ✅ `Procfile` - Tells Railway how to start the app
- ✅ `railway.json` - Railway configuration
- ✅ `.streamlit/config.toml` - Streamlit settings
- ✅ `requirements.txt` - Python dependencies

## 🔄 Auto-Updates

When you run your pipeline and it pushes to GitHub:
1. New consolidated file is committed
2. Railway detects the push
3. Automatically redeploys (~2-3 minutes)
4. Dashboard shows latest data

No manual steps needed!

## 🐛 Troubleshooting

**Dashboard shows "No consolidated files found"**
- Make sure `data/consolidated/final_consolidated_plans_*.json` exists in your repo
- Check Railway build logs for errors

**App won't start**
- Check Railway logs (visible in dashboard)
- Verify `requirements.txt` has all dependencies
- Ensure `streamlit_app.py` exists and is correct

**Need help?**
- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway

