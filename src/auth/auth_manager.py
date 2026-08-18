"""
ComputingScribe AI - Cloud Authentication Manager
Authenticates users against credentials stored securely in Google Cloud Secret Manager.
Enables secure Vertex AI access for authenticated users, while supporting Guest BYOK access.
"""

import os
import json
import time
import hmac
import hashlib
from typing import Dict, Any, Optional, Tuple
from config.gcp_config import AppConfig

# Default secret name in Google Cloud Secret Manager
DEFAULT_SECRET_ID = os.getenv("AUTH_SECRET_NAME", "computingscribe-auth-credentials").strip()

class AuthManager:
    _cached_credentials: Optional[Dict[str, Any]] = None
    _cache_timestamp: float = 0.0
    _CACHE_TTL: float = 300.0  # 5 minutes cache to minimize Secret Manager API calls
    _last_error_message: str = ""

    @classmethod
    def _hash_password(cls, password: str, salt: str = "") -> str:
        """Computes SHA-256 hash with optional salt."""
        payload = (salt + password).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def fetch_credentials_from_secret_manager(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Fetches credentials JSON from Google Cloud Secret Manager.
        Expected format in Secret Manager:
        {
          "users": {
            "gcp+allthingsagentic*2026": "YourSecretPassword",
            "admin": {
              "password_hash": "...",
              "salt": "..."
            }
          }
        }
        or simple key-value:
        {
          "gcp+allthingsagentic*2026": "YourSecretPassword"
        }
        """
        now = time.time()
        if not force_refresh and cls._cached_credentials is not None and (now - cls._cache_timestamp < cls._CACHE_TTL):
            return cls._cached_credentials

        cls._last_error_message = ""
        project_id = AppConfig.get_project_id()

        # 1. Try Google Cloud Secret Manager
        if project_id:
            try:
                from google.cloud import secretmanager
                client = secretmanager.SecretManagerServiceClient()
                name = f"projects/{project_id}/secrets/{DEFAULT_SECRET_ID}/versions/latest"
                response = client.access_secret_version(request={"name": name})
                payload = response.payload.data.decode("UTF-8")
                data = json.loads(payload)
                cls._cached_credentials = data
                cls._cache_timestamp = now
                return data
            except Exception as e:
                cls._last_error_message = f"Secret Manager fetch error: {e}"
                print(f"[AuthManager] {cls._last_error_message}")
        else:
            cls._last_error_message = "Unable to resolve Google Cloud Project ID."

        # 2. Fallback to Environment Variable for local dev / testing
        env_auth = os.getenv("AUTH_USERS_JSON", "").strip()
        if env_auth:
            try:
                data = json.loads(env_auth)
                cls._cached_credentials = data
                cls._cache_timestamp = now
                return data
            except Exception as e:
                cls._last_error_message = f"AUTH_USERS_JSON parse error: {e}"
                print(f"[AuthManager] {cls._last_error_message}")

        return {}

    @classmethod
    def verify_credentials(cls, username: str, password: str) -> Tuple[bool, str]:
        """
        Verifies username and password securely using constant-time comparison.
        Returns (is_valid, message).
        """
        username = (username or "").strip()
        password = (password or "").strip()

        if not username or not password:
            return False, "Username and password cannot be empty."

        credentials_data = cls.fetch_credentials_from_secret_manager(force_refresh=True)
        if not credentials_data:
            project_id = AppConfig.get_project_id() or "unknown"
            err_detail = cls._last_error_message or "Secret not found or empty."
            return False, f"Could not load credentials from Secret Manager (Project: '{project_id}', Secret: '{DEFAULT_SECRET_ID}'). {err_detail}"

        users_dict = credentials_data.get("users", credentials_data)

        if username not in users_dict:
            return False, "Invalid username or password."

        user_entry = users_dict[username]

        # Case A: Structured object with hash and salt
        if isinstance(user_entry, dict):
            stored_hash = user_entry.get("password_hash") or user_entry.get("hash") or ""
            salt = user_entry.get("salt") or ""
            computed_hash = cls._hash_password(password, salt)
            if stored_hash and hmac.compare_digest(stored_hash, computed_hash):
                return True, "Authentication successful."
            # Also check if stored plain password inside dict
            if "password" in user_entry:
                if hmac.compare_digest(str(user_entry["password"]), password):
                    return True, "Authentication successful."

        # Case B: Plain string password or raw SHA-256 hash string
        elif isinstance(user_entry, str):
            # Check timing-safe direct match
            if hmac.compare_digest(user_entry, password):
                return True, "Authentication successful."
            # Check timing-safe SHA-256 hash match without salt
            computed_hash = cls._hash_password(password, "")
            if hmac.compare_digest(user_entry, computed_hash):
                return True, "Authentication successful."

        return False, "Invalid username or password."
