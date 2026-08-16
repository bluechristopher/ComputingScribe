"""
EduScribe AI - GCP & Gemini Configuration Module
Handles Vertex AI, Gemini 3.7 Flash, Firestore, and Cloud Storage configurations.
Prioritizes native Vertex AI via Google Cloud IAM (zero API keys required) in production,
with seamless fallback for local development environments.
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


class VertexAIModelWrapper:
    """Unified wrapper providing standard generate_content interface across Vertex AI and GenAI SDK."""
    def __init__(self, model_name: str, client_type: str, raw_client: Any):
        self.model_name = model_name
        self.client_type = client_type
        self.raw_client = raw_client

    def generate_content(self, prompt: str, generation_config: Optional[Dict[str, Any]] = None) -> Any:
        class ResponseWrapper:
            def __init__(self, text: str):
                self.text = text

        generation_config = generation_config or {}

        # 1. Google GenAI SDK (Vertex AI mode)
        if self.client_type == "GENAI_SDK" and self.raw_client:
            try:
                config_kwargs = {}
                if "response_mime_type" in generation_config:
                    config_kwargs["response_mime_type"] = generation_config["response_mime_type"]
                res = self.raw_client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config_kwargs if config_kwargs else None
                )
                return ResponseWrapper(res.text or "")
            except Exception as e:
                print(f"[VertexAIWrapper] GenAI SDK generation error: {e}")
                # Fallback to standard generation if available
                pass

        # 2. vertexai.generative_models SDK
        elif self.client_type == "VERTEX_AI":
            try:
                from vertexai.generative_models import GenerativeModel, GenerationConfig
                g_config = None
                if "response_mime_type" in generation_config:
                    g_config = GenerationConfig(response_mime_type=generation_config["response_mime_type"])
                model = GenerativeModel(self.model_name)
                res = model.generate_content(prompt, generation_config=g_config)
                return ResponseWrapper(res.text or "")
            except Exception as e:
                print(f"[VertexAIWrapper] vertexai SDK generation error: {e}")
                pass

        # 3. google.generativeai fallback (API key mode)
        elif self.client_type == "GOOGLE_GENAI" and self.raw_client:
            try:
                model = self.raw_client.GenerativeModel(self.model_name)
                res = model.generate_content(prompt, generation_config=generation_config)
                return ResponseWrapper(res.text or "")
            except Exception as e:
                print(f"[VertexAIWrapper] google.generativeai generation error: {e}")
                pass

        raise RuntimeError("No valid Vertex AI or Gemini client response.")


class UnifiedGeminiClient:
    def __init__(self, client_type: str, raw_client: Any):
        self.client_type = client_type
        self.raw_client = raw_client

    def GenerativeModel(self, model_name: str = "gemini-3.7-flash") -> VertexAIModelWrapper:
        return VertexAIModelWrapper(model_name, self.client_type, self.raw_client)


class AppConfig:
    # Model Configuration
    DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
    FALLBACK_MODEL = "gemini-2.5-flash"
    
    # GCP Credentials & Project (Vertex AI)
    GCP_PROJECT = os.getenv("GCP_PROJECT_ID", os.getenv("GCP_PROJECT", "eduscribe-505616"))
    GCP_LOCATION = os.getenv("GCP_LOCATION", "asia-southeast1")
    GCS_BUCKET = os.getenv("GCS_BUCKET_NAME", "eduscribe-exam-assets")
    
    @classmethod
    def is_cloud_environment(cls) -> bool:
        """Checks if running inside Google Cloud Run or with service account credentials."""
        return bool(
            os.getenv("K_SERVICE") or # Cloud Run indicator
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or
            os.getenv("GCP_SA_KEY")
        )

    @classmethod
    def get_gemini_client(cls) -> Optional[UnifiedGeminiClient]:
        """
        Initializes and returns the Gemini client.
        In Google Cloud (Cloud Run), uses native Vertex AI via IAM roles with ZERO API keys.
        In local dev, uses local ADC or fallback API Key if present.
        """
        # 1. In Google Cloud Production: Vertex AI via Google GenAI SDK
        if cls.is_cloud_environment() and cls.GCP_PROJECT:
            try:
                from google import genai
                client = genai.Client(vertexai=True, project=cls.GCP_PROJECT, location=cls.GCP_LOCATION)
                return UnifiedGeminiClient("GENAI_SDK", client)
            except Exception as e1:
                try:
                    import vertexai
                    vertexai.init(project=cls.GCP_PROJECT, location=cls.GCP_LOCATION)
                    return UnifiedGeminiClient("VERTEX_AI", None)
                except Exception as e2:
                    print(f"[AppConfig] Vertex AI initialization note: {e1} / {e2}")

        # 2. Local fallback if API Key exists
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                return UnifiedGeminiClient("GOOGLE_GENAI", genai)
            except Exception as e:
                print(f"[AppConfig] Warning initializing google.generativeai: {e}")

        # 3. Try Vertex AI client as last resort
        if cls.GCP_PROJECT:
            try:
                from google import genai
                client = genai.Client(vertexai=True, project=cls.GCP_PROJECT, location=cls.GCP_LOCATION)
                return UnifiedGeminiClient("GENAI_SDK", client)
            except Exception:
                pass
                
        return None

    @classmethod
    def is_gcp_active(cls) -> bool:
        return bool(cls.GCP_PROJECT)


def load_default_preferences() -> Dict[str, Any]:
    pref_file = Path(__file__).resolve().parent / "default_preferences.json"
    if pref_file.exists():
        with open(pref_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
