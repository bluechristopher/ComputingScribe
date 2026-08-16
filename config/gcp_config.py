"""
ComputingScribe AI - GCP & Vertex AI Configuration Module
Handles Vertex AI, Gemini 3.7 Flash, Firestore, and Cloud Storage configurations.
Uses us-central1 regional endpoint for Vertex AI with zero API keys required in production,
and multi-model fallback (gemini-3.7-flash -> gemini-2.5-flash -> gemini-2.0-flash -> gemini-1.5-flash).
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
    """Unified wrapper providing generate_content interface across Vertex AI and GenAI SDK with multi-model fallback."""
    def __init__(self, model_name: str, client_type: str, raw_client: Any):
        self.model_name = model_name
        self.client_type = client_type
        self.raw_client = raw_client
        # Candidate model names on Vertex AI in order of preference
        self.model_candidates = [
            model_name,
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

        # 1. Google GenAI SDK (Vertex AI mode)
        if self.client_type == "GENAI_SDK" and self.raw_client:
            for m_candidate in self.model_candidates:
                try:
                    config_kwargs = {}
                    if "response_mime_type" in generation_config:
                        config_kwargs["response_mime_type"] = generation_config["response_mime_type"]
                    res = self.raw_client.models.generate_content(
                        model=m_candidate,
                        contents=prompt,
                        config=config_kwargs if config_kwargs else None
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

        # 3. google.generativeai fallback (API key mode)
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
    DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    FALLBACK_MODEL = "gemini-1.5-flash"
    
    # GCP Credentials & Project (Vertex AI) - Automatically detect project in Cloud Run
    GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID") or os.getenv("GCP_PROJECT") or "eduscribe-505616"
    # Vertex AI requires a valid regional location (us-central1 supports all Gemini models)
    GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
    GCS_BUCKET = os.getenv("GCS_BUCKET_NAME", "computingscribe-assets")
    
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
        Initializes and returns the Gemini client.
        In Google Cloud (Cloud Run), uses native Vertex AI on us-central1 endpoint via IAM roles.
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
                    print(f"[AppConfig] Vertex AI initialization note on {cls.GCP_LOCATION}: {e1} / {e2}")

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
