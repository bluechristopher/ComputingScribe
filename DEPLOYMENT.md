# 🚀 EduScribe AI - Deployment Guide

This guide details how to push your codebase to **GitHub** and configure **Automated CI/CD Deployment to Google Cloud Run (GCP)**.

---

## 📋 Part 1: Push Codebase to GitHub

Run these commands in PowerShell or Terminal inside the project root:

```powershell
# 1. Initialize git repository (if not already initialized)
git init

# 2. Stage all files (respects .gitignore)
git add .

# 3. Create your initial commit
git commit -m "feat: complete EduScribe AI with 2027 H2 Computing, Cambridge LaTeX, and Gemini 3.7 Flash"

# 4. Create your GitHub repository (via browser or GitHub CLI)
# If using browser, create a repository named 'ComputingScribe' or 'eduscribe-ai' on github.com

# 5. Link remote and push
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPO_NAME>.git
git push -u origin main
```

---

## ☁️ Part 2: Automated Deployment to Google Cloud Run via GitHub Actions

Whenever you push to the `main` branch, the workflow in `.github/workflows/deploy.yml` will automatically:
1. Run automated unit tests (`tests/test_pipeline.py`).
2. Build the Docker container with full TeXLive packages.
3. Push to Google Artifact Registry in Singapore (`asia-southeast1`).
4. Deploy to **Google Cloud Run** with public URL access.

### Step 1: Create a Service Account on GCP
1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Select your Project (note down the `PROJECT_ID`).
3. Navigate to **IAM & Admin** > **Service Accounts** > **Create Service Account**:
   - **Name**: `github-actions-deployer`
   - **Roles**:
     - `Cloud Run Admin`
     - `Artifact Registry Admin`
     - `Storage Admin`
     - `Service Account User`
4. Click into the newly created service account > **Keys** tab > **Add Key** > **Create new key** > Choose **JSON**.
5. Save the downloaded `.json` file.

### Step 2: Add Secrets to Your GitHub Repository
1. In your GitHub repository, go to **Settings** > **Secrets and variables** > **Actions**.
2. Click **New repository secret** and add:
   - `GCP_PROJECT_ID`: Your Google Cloud Project ID (e.g. `my-eduscribe-project`).
   - `GCP_SA_KEY`: Paste the entire contents of the downloaded Service Account JSON key file.
   *(Note: No API key secret is needed on GitHub—the deployed app operates in BYOK mode where visiting teachers supply their own Gemini API key in the UI sidebar).*

### Step 3: Trigger Deployment
Push any commit to `main`, or navigate to the **Actions** tab on GitHub and click **Run workflow**.

---

## ⚡ Part 3: Alternative — Direct 1-Click CLI Deployment

If you want to deploy directly from your local terminal using the Google Cloud SDK:

```powershell
# In PowerShell:
.\deploy.ps1
```
Or with specific project ID:
```powershell
.\deploy.ps1 -ProjectId "YOUR_GCP_PROJECT_ID"
```

The script will automatically enable the required Google Cloud APIs, build the container, and deploy to Cloud Run!
