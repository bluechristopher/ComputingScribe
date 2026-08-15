# EduScribe AI - 1-Click GCP Cloud Run Deployment Script (PowerShell)
param (
    [string]$ProjectId = "",
    [string]$Region = "asia-southeast1",
    [string]$ServiceName = "eduscribe-ai"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🚀 EduScribe AI - Google Cloud Run Deployment" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

if (-not $ProjectId) {
    $ProjectId = gcloud config get-value project 2>$null
    if (-not $ProjectId) {
        $ProjectId = Read-Host "Enter your GCP Project ID"
    }
}

Write-Host "1. Target GCP Project: $ProjectId" -ForegroundColor Green
Write-Host "2. Target Region: $Region (Singapore)" -ForegroundColor Green

# 1. Enable Required GCP APIs
Write-Host "`n[Step 1/4] Enabling Required Google Cloud APIs..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com `
    artifactregistry.googleapis.com `
    cloudbuild.googleapis.com `
    firestore.googleapis.com `
    --project=$ProjectId

# 2. Deploy directly with Cloud Build & Cloud Run
Write-Host "`n[Step 2/4] Building container and deploying to Cloud Run..." -ForegroundColor Yellow
gcloud run deploy $ServiceName `
    --source . `
    --region=$Region `
    --platform=managed `
    --allow-unauthenticated `
    --memory=2Gi `
    --cpu=2 `
    --port=8501 `
    --project=$ProjectId

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "✅ Deployment Complete! Your live app URL is listed above." -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
