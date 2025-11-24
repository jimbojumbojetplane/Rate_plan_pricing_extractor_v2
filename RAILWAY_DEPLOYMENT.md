# Railway Deployment Guide

This guide will help you deploy your Streamlit dashboard to Railway so it stays live 24/7.

## Prerequisites

1. A Railway account (sign up at https://railway.app)
2. Your GitHub repository connected to Railway
3. The consolidated JSON data files committed to your repository

## Step-by-Step Deployment

### 1. Sign up for Railway

1. Go to https://railway.app
2. Sign up with your GitHub account
3. You'll get $5 free credit to start (enough for ~1 month of a small app)

### 2. Create a New Project

1. Click "New Project" in Railway dashboard
2. Select "Deploy from GitHub repo"
3. Choose your repository: `Rate_plan_pricing_extractor_v2`
4. Railway will auto-detect it's a Python project

### 3. Configure the Service

Railway should auto-detect the setup, but verify:

1. **Build Command**: Should be auto-detected (installs from requirements.txt)
2. **Start Command**: Should use the Procfile or railway.json
   - Should be: `streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0`

### 4. Set Environment Variables (if needed)

If you have any API keys or secrets:
1. Go to your service → Variables tab
2. Add any required environment variables

### 5. Deploy

1. Railway will automatically start building and deploying
2. Watch the build logs to ensure it completes successfully
3. Once deployed, Railway will provide a URL like: `https://your-app-name.up.railway.app`

### 6. Set Up Custom Domain (Optional)

1. Go to your service → Settings → Domains
2. Click "Generate Domain" or add your own custom domain
3. Railway provides free SSL certificates automatically

## Important Notes

### Data Files

The dashboard needs the consolidated JSON files to work. Make sure:
- ✅ `data/consolidated/final_consolidated_plans_*.json` files are committed to git
- ✅ The latest file will be auto-detected by the dashboard
- ✅ When you push new consolidated files, they'll be available after Railway redeploys

### Auto-Deploy from GitHub

Railway automatically redeploys when you push to your main branch:
1. Push new consolidated file: `git push origin main`
2. Railway detects the push
3. Automatically rebuilds and redeploys (takes ~2-3 minutes)
4. Your dashboard updates with the latest data

### Cost Considerations

- **Free tier**: $5 credit/month (good for testing)
- **Hobby plan**: $5/month (512MB RAM, 1GB storage)
- **Pro plan**: $20/month (2GB RAM, 8GB storage)

For a Streamlit dashboard, the Hobby plan ($5/month) is usually sufficient.

### Monitoring

1. **Logs**: View real-time logs in Railway dashboard
2. **Metrics**: Monitor CPU, memory, and network usage
3. **Alerts**: Set up alerts for deployment failures

## Troubleshooting

### Dashboard shows "No consolidated files found"

- Make sure `data/consolidated/` directory exists in your repo
- Verify at least one `final_consolidated_plans_*.json` file is committed
- Check the file paths in the Railway logs

### App crashes on startup

- Check Railway logs for error messages
- Verify all dependencies in `requirements.txt` are correct
- Ensure Python version is compatible (Railway auto-detects)

### Slow loading

- The dashboard caches data, so first load might be slower
- Consider upgrading to a plan with more resources if needed

## Updating the Dashboard

1. Make changes to your code
2. Commit and push to GitHub: `git push origin main`
3. Railway automatically redeploys
4. Your changes go live in ~2-3 minutes

## Keeping Data Updated

Your pipeline already pushes consolidated files to GitHub. Railway will automatically:
1. Detect the new file in your repository
2. Redeploy the app
3. The dashboard will pick up the latest file automatically

No manual intervention needed! 🎉

## Support

- Railway Docs: https://docs.railway.app
- Railway Discord: https://discord.gg/railway
- Check Railway dashboard logs for detailed error messages

