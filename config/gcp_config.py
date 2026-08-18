"""
ComputingScribe AI - Configuration Module
Handles Gemini Models (Gemini 3.7 Flash) and dual access modes:
1. Guest Entry: Bring Your Own Key (BYOK) via Google AI Studio API Key.
2. Authenticated Access: Enterprise Google Cloud Vertex AI (Gemini 3.7 Flash).
"""

import os
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STORAGE_DIR = BASE_DIR / "data_store"
LOCAL_SESSIONS_DIR = STORAGE_DIR / "sessions"
LOCAL_PREFS_DIR = STORAGE_DIR / "preferences"

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_PREFS_DIR.mkdir(parents=True, exist_ok=True)


class GeminiModelWrapper:
    """Unified wrapper providing generate_content interface using direct Gemini API key or Vertex AI."""
    def __init__(self, model_name: str, client_type: str, raw_client: Any):
        self.model_name = str(model_name).strip()
        self.client_type = client_type
        self.raw_client = raw_client
        # Candidate model names in order of capability and speed (Gemini 3.7 Flash first)
        self.model_candidates = [
            self.model_name,
            "gemini-3.7-flash",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash"
        ]

    def generate_content(self, prompt: str, generation_config: Optional[Dict[str, Any]] = None) -> Any:
        class ResponseWrapper:
            def __init__(self, text: str):
                self.text = text

        generation_config = generation_config or {}

        # 1. Google GenAI SDK (Direct API Key mode)
        if self.client_type == "GENAI_SDK_KEY" and self.raw_client:
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
                    print(f"[GeminiModelWrapper] Google GenAI SDK error on model {m_candidate}: {e}")
                    continue

        # 2. Google GenAI SDK with Vertex AI (Authenticated Enterprise Mode)
        elif self.client_type == "GENAI_VERTEX" and self.raw_client:
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
                    print(f"[GeminiModelWrapper] GenAI Vertex AI error on model {m_candidate}: {e}")
                    continue

        # 3. Legacy Vertex AI SDK
        elif self.client_type == "VERTEX_AI" and self.raw_client:
            for m_candidate in self.model_candidates:
                try:
                    from vertexai.generative_models import GenerativeModel
                    model = GenerativeModel(m_candidate)
                    res = model.generate_content(prompt, generation_config=generation_config)
                    if res and res.text:
                        return ResponseWrapper(res.text)
                except Exception as e:
                    print(f"[GeminiModelWrapper] Legacy Vertex AI error on model {m_candidate}: {e}")
                    continue

        # 4. Legacy google.generativeai fallback
        elif self.client_type == "GOOGLE_GENAI" and self.raw_client:
            for m_candidate in self.model_candidates:
                try:
                    model = self.raw_client.GenerativeModel(m_candidate)
                    res = model.generate_content(prompt, generation_config=generation_config)
                    if res and res.text:
                        return ResponseWrapper(res.text)
                except Exception as e:
                    print(f"[GeminiModelWrapper] google.generativeai error on model {m_candidate}: {e}")
                    continue

        raise RuntimeError("No valid Gemini model response received. Please check your API key (Guest BYOK) or Google Cloud Vertex AI configuration.")


class UnifiedGeminiClient:
    def __init__(self, client_type: str, raw_client: Any):
        self.client_type = client_type
        self.raw_client = raw_client

    def GenerativeModel(self, model_name: str = "gemini-3.7-flash") -> GeminiModelWrapper:
        return GeminiModelWrapper(model_name, self.client_type, self.raw_client)


class AppConfig:
    # Model Configuration: Gemini 3.7 Flash Primary
    DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash").strip()
    FALLBACK_MODEL = "gemini-2.5-flash"
    
    _raw_project = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or ""
    GCP_PROJECT = _raw_project.strip()
    
    _raw_location = os.getenv("GCP_LOCATION", "us-central1")
    GCP_LOCATION = _raw_location.strip()
    GCS_BUCKET = os.getenv("GCS_BUCKET_NAME", "computingscribe-assets").strip()

    # Active Auth Mode: "byok" or "vertex_ai"
    ACTIVE_AUTH_MODE: str = os.getenv("ACTIVE_AUTH_MODE", "byok").strip()

    @classmethod
    def get_project_id(cls) -> str:
        """Dynamically discovers the active Google Cloud Project ID."""
        if cls.GCP_PROJECT:
            return cls.GCP_PROJECT
        for env_var in ["GOOGLE_CLOUD_PROJECT", "GCP_PROJECT_ID", "GCP_PROJECT"]:
            val = os.getenv(env_var, "").strip()
            if val:
                cls.GCP_PROJECT = val
                return val
        # Try google.auth.default()
        try:
            import google.auth
            _, auth_project = google.auth.default()
            if auth_project:
                cls.GCP_PROJECT = auth_project
                return auth_project
        except Exception:
            pass
        # Try metadata server (on Cloud Run / Compute Engine)
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://metadata.google.internal/computeMetadata/v1/project/project-id",
                headers={"Metadata-Flavor": "Google"}
            )
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                meta_p = resp.read().decode("utf-8").strip()
                if meta_p:
                    cls.GCP_PROJECT = meta_p
                    return meta_p
        except Exception:
            pass
        return ""
    
    @classmethod
    def is_cloud_environment(cls) -> bool:
        """Checks if running inside a cloud environment with persistent GCP services."""
        return bool(
            os.getenv("K_SERVICE") or
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or
            cls.get_project_id()
        )

    @classmethod
    def set_auth_mode(cls, mode: str):
        """Sets active auth mode: 'byok' or 'vertex_ai'."""
        cls.ACTIVE_AUTH_MODE = "vertex_ai" if mode == "vertex_ai" else "byok"

    @classmethod
    def get_gemini_client(cls, auth_mode: Optional[str] = None) -> Optional[UnifiedGeminiClient]:
        """
        Initializes and returns the Gemini client based on active auth mode:
        1. 'vertex_ai': Uses Google Cloud Vertex AI (Gemini 3.7 Flash) with GCP credentials.
        2. 'byok': Uses educator's self-supplied GEMINI_API_KEY via Google GenAI SDK.
        """
        effective_mode = auth_mode or cls.ACTIVE_AUTH_MODE or "byok"

        # --- A. Vertex AI Mode (Authenticated Access) ---
        if effective_mode == "vertex_ai":
            project = cls.get_project_id()
            location = cls.GCP_LOCATION or "asia-southeast1"
            
            # 1. Try google.genai with vertexai=True
            try:
                from google import genai
                client = genai.Client(vertexai=True, project=project or None, location=location)
                return UnifiedGeminiClient("GENAI_VERTEX", client)
            except Exception as e:
                print(f"[AppConfig] genai Vertex AI init note: {e}")

            # 2. Try legacy vertexai SDK
            try:
                import vertexai
                if project:
                    vertexai.init(project=project, location=location)
                else:
                    vertexai.init(location=location)
                return UnifiedGeminiClient("VERTEX_AI", vertexai)
            except Exception as e2:
                print(f"[AppConfig] vertexai init note: {e2}")

        # --- B. BYOK Mode (Guest Entry with User API Key) ---
        api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

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
