"""
EduScribe AI - Session Manager Module
Manages CRUD lifecycle for exam authoring sessions in Firestore, Cloud Storage, and Local Store.
Provides packaging utilities to create downloadable .zip bundles.
"""

import os
import json
import re
import shutil
import zipfile
import hashlib
import mimetypes
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime, timezone
from config.gcp_config import AppConfig, LOCAL_SESSIONS_DIR

class ExamSession:
    def __init__(
        self,
        session_id: str,
        title: str = "Untitled Exam Session",
        teacher_id: str = "default_teacher",
        paper_type: str = "practical", # "practical" or "theory"
        category: str = "sec1_linear_adts",
        syllabus_code: str = "9569",
        paper_number: str = "02",
        institution: str = "HelloWorld Junior College",
        exam_year: str = "2027",
        exam_series: str = "PRELIM",
        blueprint: Optional[Dict[str, Any]] = None,
        latex_source: str = "",
        mark_scheme_source: str = "",
        generated_datasets: Optional[List[Dict[str, str]]] = None,
        starter_files: Optional[List[Dict[str, str]]] = None,
        image_assets: Optional[List[Dict[str, str]]] = None,
        questions: Optional[List[Dict[str, Any]]] = None,
        status: str = "draft",
        compilation_logs: str = "",
        pdf_path: Optional[str] = None
    ):
        self.session_id = session_id
        self.title = title
        self.teacher_id = teacher_id
        self.paper_type = paper_type
        self.category = category
        self.syllabus_code = syllabus_code
        self.paper_number = paper_number
        self.institution = institution
        self.exam_year = exam_year
        self.exam_series = exam_series
        self.blueprint = blueprint or {}
        self.latex_source = latex_source
        self.mark_scheme_source = mark_scheme_source
        self.generated_datasets = generated_datasets or []
        self.starter_files = starter_files or []
        self.image_assets = image_assets or []
        self.questions = questions or []
        self.status = status
        self.compilation_logs = compilation_logs
        self.pdf_path = pdf_path
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "teacher_id": self.teacher_id,
            "paper_type": self.paper_type,
            "category": self.category,
            "syllabus_code": self.syllabus_code,
            "paper_number": self.paper_number,
            "institution": self.institution,
            "exam_year": self.exam_year,
            "exam_series": self.exam_series,
            "blueprint": self.blueprint,
            "latex_source": self.latex_source,
            "mark_scheme_source": self.mark_scheme_source,
            "generated_datasets": self.generated_datasets,
            "starter_files": self.starter_files,
            "image_assets": self.image_assets,
            "questions": self.questions,
            "status": self.status,
            "compilation_logs": self.compilation_logs,
            "pdf_path": self.pdf_path,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExamSession":
        return cls(
            session_id=data.get("session_id", ""),
            title=data.get("title", "Untitled Session"),
            teacher_id=data.get("teacher_id", "default_teacher"),
            paper_type=data.get("paper_type", "practical"),
            category=data.get("category", "sec1_linear_adts"),
            syllabus_code=data.get("syllabus_code", "9569"),
            paper_number=data.get("paper_number", "02"),
            institution=data.get("institution", "HelloWorld Junior College"),
            exam_year=data.get("exam_year", "2027"),
            exam_series=data.get("exam_series", "PRELIM"),
            blueprint=data.get("blueprint", {}),
            latex_source=data.get("latex_source", ""),
            mark_scheme_source=data.get("mark_scheme_source", ""),
            generated_datasets=data.get("generated_datasets", []),
            starter_files=data.get("starter_files", []),
            image_assets=data.get("image_assets", []),
            questions=data.get("questions", []),
            status=data.get("status", "draft"),
            compilation_logs=data.get("compilation_logs", ""),
            pdf_path=data.get("pdf_path")
        )

class SessionManager:
    def __init__(self):
        self.firestore_db = None
        self.gcs_client = None
        self._init_cloud_clients()

    def _init_cloud_clients(self):
        if AppConfig.is_cloud_environment() and AppConfig.GCP_PROJECT:
            try:
                from google.cloud import firestore, storage
                self.firestore_db = firestore.Client(project=AppConfig.GCP_PROJECT)
                self.gcs_client = storage.Client(project=AppConfig.GCP_PROJECT)
            except Exception as e:
                print(f"[SessionManager] Cloud clients initialization failed, using local storage: {e}")
                self.firestore_db = None
                self.gcs_client = None

    def _get_session_dir(self, session_id: str) -> Path:
        sess_dir = LOCAL_SESSIONS_DIR / session_id
        sess_dir.mkdir(parents=True, exist_ok=True)
        return sess_dir

    def save_session(self, session: ExamSession) -> bool:
        """Saves session metadata and file artefacts locally and to Cloud if configured."""
        session.updated_at = datetime.now(timezone.utc).isoformat()
        session_dir = self._get_session_dir(session.session_id)
        
        # Save JSON metadata locally
        meta_path = session_dir / "session.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2)

        # Save individual source artefacts
        if session.latex_source:
            with open(session_dir / "paper.tex", "w", encoding="utf-8") as f:
                f.write(session.latex_source)
        if session.mark_scheme_source:
            with open(session_dir / "mark_scheme.tex", "w", encoding="utf-8") as f:
                f.write(session.mark_scheme_source)

        # Save datasets
        if session.generated_datasets:
            ds_dir = session_dir / "datasets"
            ds_dir.mkdir(exist_ok=True)
            for ds in session.generated_datasets:
                filename = ds.get("filename", "dataset.csv")
                content = ds.get("content", "")
                with open(ds_dir / filename, "w", encoding="utf-8") as f:
                    f.write(content)

        # Save starter files
        if session.starter_files:
            sf_dir = session_dir / "starter_files"
            sf_dir.mkdir(exist_ok=True)
            for sf in session.starter_files:
                filename = sf.get("filename", "starter.py")
                content = sf.get("content", "")
                with open(sf_dir / filename, "w", encoding="utf-8") as f:
                    f.write(content)

        # Sync with Firestore
        if self.firestore_db:
            try:
                self.firestore_db.collection("exam_sessions").document(session.session_id).set(session.to_dict(), timeout=2.0)
            except Exception as e:
                print(f"[SessionManager] Firestore save note: {e}")

        return True

    def save_image_asset(self, session: ExamSession, original_name: str, content: bytes, mime_type: str = "") -> Dict[str, str]:
        """Stores a browser- and LaTeX-compatible image under its session assets folder."""
        suffix = Path(original_name).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("Only PNG and JPEG images are supported.")

        stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(original_name).stem).strip("-") or "image"
        digest = hashlib.sha256(content).hexdigest()[:12]
        filename = f"{stem}-{digest}{suffix}"
        session_dir = self._get_session_dir(session.session_id)
        asset_dir = session_dir / "assets"
        asset_dir.mkdir(exist_ok=True)
        (asset_dir / filename).write_bytes(content)

        asset = {
            "filename": filename,
            "path": f"assets/{filename}",
            "mime_type": mime_type or mimetypes.guess_type(filename)[0] or "image/png",
            "original_name": original_name,
        }
        session.image_assets = [item for item in session.image_assets if item.get("filename") != filename]
        session.image_assets.append(asset)
        self.save_session(session)
        return asset

    def get_session(self, session_id: str) -> Optional[ExamSession]:
        """Loads a session from Firestore or local storage."""
        # Try Firestore first with strict timeout
        if self.firestore_db:
            try:
                doc = self.firestore_db.collection("exam_sessions").document(session_id).get(timeout=2.0)
                if doc.exists:
                    return ExamSession.from_dict(doc.to_dict())
            except Exception as e:
                print(f"[SessionManager] Firestore get note: {e}")

        # Local fallback
        meta_path = self._get_session_dir(session_id) / "session.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return ExamSession.from_dict(data)
            except Exception as e:
                print(f"[SessionManager] Local session load error: {e}")

        return None

    def list_sessions(self, teacher_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all saved sessions with summary details."""
        sessions = []

        # Try Firestore with strict 2-second timeout
        if self.firestore_db:
            try:
                query = self.firestore_db.collection("exam_sessions")
                if teacher_id:
                    query = query.where("teacher_id", "==", teacher_id)
                docs = query.limit(20).get(timeout=2.0)
                for doc in docs:
                    d = doc.to_dict()
                    sessions.append({
                        "session_id": d.get("session_id"),
                        "title": d.get("title"),
                        "paper_type": d.get("paper_type"),
                        "category": d.get("category"),
                        "syllabus_code": d.get("syllabus_code"),
                        "updated_at": d.get("updated_at", ""),
                        "status": d.get("status", "draft")
                    })
                if sessions:
                    return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
            except Exception as e:
                print(f"[SessionManager] Firestore list note: {e}")

        # Local directory scan fallback
        if LOCAL_SESSIONS_DIR.exists():
            for s_dir in LOCAL_SESSIONS_DIR.iterdir():
                if s_dir.is_dir():
                    meta_file = s_dir / "session.json"
                    if meta_file.exists():
                        try:
                            with open(meta_file, "r", encoding="utf-8") as f:
                                d = json.load(f)
                                if not teacher_id or d.get("teacher_id") == teacher_id:
                                    sessions.append({
                                        "session_id": d.get("session_id"),
                                        "title": d.get("title"),
                                        "paper_type": d.get("paper_type"),
                                        "category": d.get("category"),
                                        "syllabus_code": d.get("syllabus_code"),
                                        "updated_at": d.get("updated_at", ""),
                                        "status": d.get("status", "draft")
                                    })
                        except Exception:
                            continue

        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)

    def delete_session(self, session_id: str) -> bool:
        """Deletes a session from Firestore and local disk."""
        if self.firestore_db:
            try:
                self.firestore_db.collection("exam_sessions").document(session_id).delete()
            except Exception as e:
                print(f"[SessionManager] Firestore delete error: {e}")

        session_dir = LOCAL_SESSIONS_DIR / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
            return True
        return False

    def export_bundle_zip(self, session_id: str) -> Optional[bytes]:
        """Creates a downloadable .zip archive of all session artefacts."""
        session_dir = self._get_session_dir(session_id)
        if not session_dir.exists():
            return None

        zip_path = session_dir / f"{session_id}_bundle.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(session_dir):
                for file in files:
                    if file.endswith(".zip"):
                        continue
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(session_dir)
                    zipf.write(full_path, rel_path)

        with open(zip_path, "rb") as f:
            return f.read()
