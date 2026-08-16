"""
ComputingScribe AI - GCP & Vertex AI Configuration Module
Handles Vertex AI, Gemini Models, Firestore, and Cloud Storage configurations.
Supports dual enterprise tiers:
- Tier 1: Native Vertex AI via Google Cloud IAM (zero keys).
- Tier 2 (Secure Fallback): Google Cloud Secret Manager injected GEMINI_API_KEY via Google GenAI SDK.
"""

import os
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "data_store"
LOCAL_SESSIONS_DIR = STORAGE_DIR / "sessions"
LOCAL_PREFS_DIR = STORAGE_DIR / "preferences"

LOCAL_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_PREFS_DIR.mkdir(parents=True, exist_ok=True)


class VertexAIModelWrapper:
    """Unified wrapper providing generate_content interface across Vertex AI, GenAI API Key, and SDKs."""
    def __init__(self, model_name: str, client_type: str, raw_client: Any):
        self.model_name = str(model_name).strip()
        self.client_type = client_type
        self.raw_client = raw_client
        # Candidate model names in order of speed and capability
        self.model_candidates = [
            self.model_name,
            "gemini-2.5-flash",
            "gemini-3.7-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash"
        ]

    def generate_content(self, prompt: str, generation_config: Optional[Dict[str, Any]] = None) -> Any:
        class ResponseWrapper:
            def __init__(self, text: str):
                self.text = text

        generation_config = generation_config or {}

        # 1. Google GenAI SDK (Vertex AI mode or Secure API Key mode)
        if self.client_type in ["GENAI_SDK", "GENAI_SDK_KEY"] and self.raw_client:
            for m_candidate in self.model_candidates:
                try:
                    from google.genai import types
                    req_config = None
                    if "response_mime_type" in generation_config:
                        req_config = types.GenerateContentConfig(response_mime_type=generation_config["response_mime_type"])
                    res = self.raw_client.models.generate_content(
                        model=m_candidate,
                        contents=prompt,
                        config=req_config
                    )
                    if res and res.text:
                        return ResponseWrapper(res.text)
                except Exception as e:
                    print(f"[VertexAIWrapper] GenAI SDK error on model {m_candidate}: {e}")
                    continue

        # 2. vertexai.generative_models SDK
        elif self.client_type == "VERTEX_AI":
            for m_candidate in self.model_candidates:
                try:
                    from vertexai.generative_models import GenerativeModel, GenerationConfig
                    g_config = None
                    if "response_mime_type" in generation_config:
                        g_config = GenerationConfig(response_mime_type=generation_config["response_mime_type"])
                    model = GenerativeModel(m_candidate)
                    res = model.generate_content(prompt, generation_config=g_config)
                    if res and res.text:
                        return ResponseWrapper(res.text)
                except Exception as e:
                    print(f"[VertexAIWrapper] vertexai SDK error on model {m_candidate}: {e}")
                    continue

        # 3. google.generativeai fallback (Legacy API key mode)
        elif self.client_type == "GOOGLE_GENAI" and self.raw_client:
            for m_candidate in self.model_candidates:
                try:
                    model = self.raw_client.GenerativeModel(m_candidate)
                    res = model.generate_content(prompt, generation_config=generation_config)
                    if res and res.text:
                        return ResponseWrapper(res.text)
                except Exception as e:
                    print(f"[VertexAIWrapper] google.generativeai error on model {m_candidate}: {e}")
                    continue

        raise RuntimeError("No valid Vertex AI or Gemini model response received.")


class UnifiedGeminiClient:
    def __init__(self, client_type: str, raw_client: Any):
        self.client_type = client_type
        self.raw_client = raw_client

    def GenerativeModel(self, model_name: str = "gemini-2.5-flash") -> VertexAIModelWrapper:
        return VertexAIModelWrapper(model_name, self.client_type, self.raw_client)


class AppConfig:
    # Model Configuration
    DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    FALLBACK_MODEL = "gemini-1.5-flash"
    
    _raw_project = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or "eduscribe-ai"
    GCP_PROJECT = _raw_project.strip()
    
    _raw_location = os.getenv("GCP_LOCATION", "us-central1")
    GCP_LOCATION = _raw_location.strip()
    GCS_BUCKET = os.getenv("GCS_BUCKET_NAME", "computingscribe-assets").strip()
    
    @classmethod
    def is_cloud_environment(cls) -> bool:
        """Checks if running inside Google Cloud Run or with service account credentials."""
        return bool(
            os.getenv("K_SERVICE") or
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or
            os.getenv("GCP_SA_KEY") or
            os.getenv("GOOGLE_CLOUD_PROJECT")
        )

    @classmethod
    def get_gemini_client(cls) -> Optional[UnifiedGeminiClient]:
        """
        Initializes and returns the Gemini client with priority hierarchy:
        Option 1 (Primary): Secure Secret Manager / Environment GEMINI_API_KEY via Google GenAI SDK.
        Option 2 (Secondary Fallback): Native Vertex AI on us-central1 via IAM.
        Option 3 (Tertiary Fallback): Legacy SDK.
        """
        api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

        # 1. Option 1 (PRIMARY): Secure Secret Manager API Key via Google GenAI SDK
        if api_key:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                return UnifiedGeminiClient("GENAI_SDK_KEY", client)
            except Exception as e:
                try:
                    import google.generativeai as legacy_genai
                    legacy_genai.configure(api_key=api_key)
                    return UnifiedGeminiClient("GOOGLE_GENAI", legacy_genai)
                except Exception as e2:
                    print(f"[AppConfig] Note initializing GenAI API Key: {e} / {e2}")

        # 2. Option 2 (SECONDARY FALLBACK): Native Vertex AI via Google GenAI SDK / IAM
        if cls.is_cloud_environment() or cls.GCP_PROJECT:
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
                    print(f"[AppConfig] Vertex AI initialization note on {cls.GCP_LOCATION}: {e1} / {e2}")

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
