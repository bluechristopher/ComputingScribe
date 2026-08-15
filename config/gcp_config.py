"""
EduScribe AI - GCP & Gemini Configuration Module
Handles Vertex AI, Gemini 3.7 Flash, Firestore, and Cloud Storage configurations.
Provides seamless fallback for local development or API Key based usage.
"""

import os
import json
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "data_store"
LOCAL_SESSIONS_DIR = STORAGE_DIR / "sessions"
LOCAL_PREFS_DIR = STORAGE_DIR / "preferences"

# Ensure local directories exist for offline/fallback mode
LOCAL_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_PREFS_DIR.mkdir(parents=True, exist_ok=True)

class AppConfig:
    # Model Configuration
    DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
    FALLBACK_MODEL = "gemini-2.5-flash"
    
    # GCP Credentials & Project
    GCP_PROJECT = os.getenv("GCP_PROJECT", "")
    GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
    GCS_BUCKET = os.getenv("GCS_BUCKET_NAME", "eduscribe-exam-assets")
    
    # Direct Gemini API Key
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    @classmethod
    def get_gemini_client(cls):
        """
        Initializes and returns the Gemini client.
        Prioritizes google.genai or google.generativeai with GEMINI_API_KEY or Vertex AI.
        """
        api_key = cls.GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY", "")
        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                return genai
            except Exception as e:
                print(f"[AppConfig] Warning initializing google.generativeai: {e}")
        
        # If vertex ai project is configured
        if cls.GCP_PROJECT:
            try:
                import vertexai
                from vertexai.generative_models import GenerativeModel
                vertexai.init(project=cls.GCP_PROJECT, location=cls.GCP_LOCATION)
                return "VERTEX_AI"
            except Exception as e:
                print(f"[AppConfig] Vertex AI init skipped: {e}")
                
        return None

    @classmethod
    def is_gcp_active(cls) -> bool:
        return bool(cls.GCP_PROJECT and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))

def load_default_preferences() -> Dict[str, Any]:
    pref_file = Path(__file__).resolve().parent / "default_preferences.json"
    if pref_file.exists():
        with open(pref_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
