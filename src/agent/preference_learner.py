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
    include_starter_code: bool = True
    include_dataset_generation: bool = True
    custom_directives: list[str] = Field(default_factory=list)

class PreferenceLearner:
    def __init__(self, teacher_id: str = "default_teacher"):
        self.teacher_id = teacher_id
        self.firestore_db = None
        self._init_firestore()

    def _init_firestore(self):
        if AppConfig.is_gcp_active():
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
                doc = doc_ref.get()
                if doc.exists:
                    data = doc.to_dict()
                    return data.get("learned_styles", {})
            except Exception as e:
                print(f"[PreferenceLearner] Firestore fetch error: {e}")

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

    def get_style_for_category(self, category: str) -> Dict[str, Any]:
        """Retrieves learned style for a specific syllabus category."""
        all_styles = self.load_all_styles()
        if category in all_styles:
            return all_styles[category]
        # Return sensible default
        return {
            "category": category,
            "preferred_depth": "long_contextual" if "practical" in category.lower() else "short_direct",
            "task_count": 4 if "practical" in category.lower() else 5,
            "total_marks": 75,
            "rubric_style": "granular_partial_credit",
            "include_starter_code": True,
            "include_dataset_generation": "practical" in category.lower(),
            "custom_directives": []
        }

    def save_style_for_category(self, category: str, style_data: Dict[str, Any]):
        """Persists updated style preferences in Firestore & local cache."""
        all_styles = self.load_all_styles()
        all_styles[category] = style_data

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
                doc_ref.set({"learned_styles": all_styles}, merge=True)
            except Exception as e:
                print(f"[PreferenceLearner] Error saving to Firestore: {e}")

    def adapt_preferences_from_feedback(self, category: str, user_prompt: str, educator_feedback: str = ""):
        """
        Uses Gemini 3.7 Flash to extract updated pedagogical preferences from natural educator interactions.
        """
        prompt_text = f"""
You are an expert pedagogical metadata extractor.
Given the educator's request and feedback, extract updated authoring style preferences.

Category: {category}
Educator Input: {user_prompt}
Educator Feedback / Edits: {educator_feedback}

Return a valid JSON object matching these fields:
{{
  "preferred_depth": "short_direct" or "long_contextual",
  "task_count": integer (1 to 8),
  "total_marks": integer (10 to 100),
  "rubric_style": "granular_partial_credit" or "cambridge_ao_breakdown" or "point_per_distinct_fact",
  "custom_directives": ["bullet", "point", "directives"]
}}
"""
        try:
            client = AppConfig.get_gemini_client()
            if client and hasattr(client, "GenerativeModel"):
                model = client.GenerativeModel(AppConfig.DEFAULT_MODEL)
                response = model.generate_content(
                    prompt_text,
                    generation_config={"response_mime_type": "application/json"}
                )
                extracted = json.loads(response.text)
                current = self.get_style_for_category(category)
                current.update(extracted)
                self.save_style_for_category(category, current)
                return current
        except Exception as e:
            print(f"[PreferenceLearner] Adaptive learning extraction skipped/failed: {e}")
        
        return self.get_style_for_category(category)
