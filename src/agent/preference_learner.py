"""
EduScribe AI - Preference Learner Module
Learns educator habits, question depth, and formatting preferences across categories.
Persists preferences in Google Cloud Firestore with a local JSON cache fallback.
"""

import os
import json
from typing import Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel, Field
from config.gcp_config import AppConfig, LOCAL_PREFS_DIR, load_default_preferences

class CategoryStyle(BaseModel):
    category: str
    preferred_depth: str = Field(default="long_contextual", description="'short_direct' or 'long_contextual'")
    task_count: int = Field(default=4, description="Standard number of questions or tasks")
    total_marks: int = Field(default=75, description="Target total mark allotment")
    rubric_style: str = Field(default="granular_partial_credit", description="Rubric breakdown preference")
    python_signature_style: str = Field(default="plain_no_type_hints", description="Standard Python signature with no return arrows or input type hints (e.g. def search(arr, target))")
    include_starter_code: bool = True
    include_dataset_generation: bool = True
    custom_directives: list[str] = Field(default_factory=list)

class PreferenceLearner:
    def __init__(self, teacher_id: str = "default_teacher"):
        self.teacher_id = teacher_id
        self.firestore_db = None
        self._init_firestore()

    def _init_firestore(self):
        if AppConfig.is_cloud_environment() and AppConfig.GCP_PROJECT:
            try:
                from google.cloud import firestore
                self.firestore_db = firestore.Client(project=AppConfig.GCP_PROJECT)
            except Exception as e:
                print(f"[PreferenceLearner] Firestore client init failed, using local cache: {e}")
                self.firestore_db = None

    def _get_local_filepath(self) -> Path:
        return LOCAL_PREFS_DIR / f"{self.teacher_id}_prefs.json"

    def load_all_styles(self) -> Dict[str, Any]:
        """Loads all learned styles for this teacher from Firestore or local fallback."""
        if self.firestore_db:
            try:
                doc_ref = self.firestore_db.collection("teacher_profiles").document(self.teacher_id)
                doc = doc_ref.get(timeout=2.0)
                if doc.exists:
                    data = doc.to_dict()
                    return data.get("learned_styles", {})
            except Exception as e:
                print(f"[PreferenceLearner] Firestore fetch note: {e}")

        # Local fallback
        local_file = self._get_local_filepath()
        if local_file.exists():
            try:
                with open(local_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[PreferenceLearner] Local pref read error: {e}")

        # Default fallback
        defaults = load_default_preferences()
        default_profile = defaults.get("teacher_profiles", {}).get("default_teacher", {})
        return default_profile.get("learned_styles", {})

    def get_style(self, category: str = "generic") -> Dict[str, Any]:
        """Retrieves learned generic style preferences for this educator across topics."""
        all_styles = self.load_all_styles()
        # 1. First check generic global style
        if "generic" in all_styles:
            base_style = dict(all_styles["generic"])
            if category != "generic" and category in all_styles:
                base_style.update(all_styles[category])
            return base_style
        
        # 2. Check specific category if present
        if category in all_styles:
            return all_styles[category]
            
        # 3. Default generic preference
        return {
            "category": "generic",
            "preferred_depth": "long_contextual",
            "task_count": 4,
            "total_marks": 100,
            "rubric_style": "granular_partial_credit",
            "python_signature_style": "plain_no_type_hints",
            "include_starter_code": True,
            "include_dataset_generation": True,
            "custom_directives": []
        }

    def get_style_for_category(self, category: str = "generic") -> Dict[str, Any]:
        """Alias for get_style for backward compatibility."""
        return self.get_style(category)

    def save_style(self, style_data: Dict[str, Any], category: str = "generic"):
        """Persists updated generic style preferences in Firestore & local cache."""
        all_styles = self.load_all_styles()
        all_styles[category] = style_data
        if category != "generic" and "generic" not in all_styles:
            all_styles["generic"] = style_data

        # Save to local cache
        try:
            local_file = self._get_local_filepath()
            with open(local_file, "w", encoding="utf-8") as f:
                json.dump(all_styles, f, indent=2)
        except Exception as e:
            print(f"[PreferenceLearner] Error writing local preference file: {e}")

        # Save to Firestore
        if self.firestore_db:
            try:
                doc_ref = self.firestore_db.collection("teacher_profiles").document(self.teacher_id)
                doc_ref.set({"learned_styles": all_styles}, merge=True, timeout=2.0)
            except Exception as e:
                print(f"[PreferenceLearner] Note saving to Firestore: {e}")

    def save_style_for_category(self, category: str, style_data: Dict[str, Any]):
        """Alias for save_style."""
        self.save_style(style_data, category)

    def adapt_preferences_from_feedback(self, category: str = "generic", user_prompt: str = "", educator_feedback: str = ""):
        """
        Uses Gemini 3.7 Flash to extract updated generic pedagogical preferences from natural educator feedback.
        """
        prompt_text = f"""
You are an expert pedagogical metadata extractor.
Given the educator's request and feedback, extract updated generic authoring style preferences.

Category Context: {category}
Educator Input: {user_prompt}
Feedback: {educator_feedback}

Return a valid JSON object matching this schema:
{{
  "category": "generic",
  "preferred_depth": "long_contextual" or "short_direct",
  "task_count": integer,
  "total_marks": integer,
  "rubric_style": "granular_partial_credit" or "point_based",
  "python_signature_style": "plain_no_type_hints",
  "include_starter_code": boolean,
  "include_dataset_generation": boolean,
  "custom_directives": ["directive 1", "directive 2"]
}}
"""
        client = AppConfig.get_gemini_client()
        if client and hasattr(client, "GenerativeModel"):
            try:
                model = client.GenerativeModel(AppConfig.DEFAULT_MODEL)
                response = model.generate_content(
                    prompt_text,
                    generation_config={"response_mime_type": "application/json"}
                )
                updated_style = json.loads(response.text)
                self.save_style(updated_style, "generic")
                return updated_style
            except Exception as e:
                print(f"[PreferenceLearner] Gemini style extraction error: {e}")

        # Fallback manual update
        current = self.get_style("generic")
        if "short" in educator_feedback.lower() or "direct" in educator_feedback.lower():
            current["preferred_depth"] = "short_direct"
        elif "context" in educator_feedback.lower() or "detailed" in educator_feedback.lower():
            current["preferred_depth"] = "long_contextual"
        if educator_feedback:
            current.setdefault("custom_directives", []).append(educator_feedback)
        self.save_style(current, "generic")
        return current
