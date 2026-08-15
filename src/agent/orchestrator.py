"""
EduScribe AI - Orchestrator Module
The central agentic brain executing the 5-step autonomous exam authoring lifecycle.
"""

import uuid
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path

from src.agent.preference_learner import PreferenceLearner
from src.agent.session_manager import SessionManager, ExamSession
from src.ingestion.rag_retriever import RAGRetriever
from src.ingestion.document_parser import DocumentParser
from src.generators.dataset_generator import DatasetGenerator, SyntheticDataset
from src.generators.question_author import QuestionAuthor, ExamBlueprint
from src.sandbox.latex_compiler import LaTeXCompiler, LaTeXCompilationResult
from config.gcp_config import LOCAL_SESSIONS_DIR

class ExamGenerationProgress:
    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log_callback = log_callback

    def notify(self, step: str, message: str):
        if self.log_callback:
            self.log_callback(step, message)
        print(f"[{step}] {message}")

class EduScribeOrchestrator:
    def __init__(self, teacher_id: str = "default_teacher"):
        self.teacher_id = teacher_id
        self.preference_learner = PreferenceLearner(teacher_id=teacher_id)
        self.session_manager = SessionManager()
        self.rag_retriever = RAGRetriever()
        self.dataset_generator = DatasetGenerator()
        self.question_author = QuestionAuthor()
        self.latex_compiler = LaTeXCompiler(max_healing_attempts=3)

    def set_teacher_id(self, teacher_id: str):
        self.teacher_id = teacher_id
        self.preference_learner = PreferenceLearner(teacher_id=teacher_id)

    def ingest_past_papers(self, uploaded_files: List[Any]) -> int:
        """Parses and indexes past papers into the RAG retriever."""
        indexed_count = 0
        for uf in uploaded_files:
            file_bytes = uf.getvalue() if hasattr(uf, "getvalue") else uf.read()
            doc_data = DocumentParser.parse_file(file_bytes, uf.name)
            self.rag_retriever.add_document(doc_data)
            indexed_count += 1
        return indexed_count

    def generate_exam_package(
        self,
        user_prompt: str,
        paper_type: str = "practical", # "practical" or "theory"
        category: str = "sec1_linear_adts",
        session_id: Optional[str] = None,
        syllabus_code: str = "9569",
        paper_number: str = "02",
        institution: str = "Anderson Serangoon Junior College",
        exam_year: str = "2027",
        exam_series: str = "PRELIM",
        progress: Optional[ExamGenerationProgress] = None
    ) -> ExamSession:
        """
        Autonomous 5-Step Pipeline:
        1. Memory & Style Retrieval
        2. Blueprint Proposer
        3. Synthetic Dataset & LaTeX Code Synthesis
        4. Self-Healing Compilation Loop
        5. Session Sync & Bundle Packaging
        """
        prog = progress or ExamGenerationProgress()
        sess_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        session_dir = LOCAL_SESSIONS_DIR / sess_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # -------------------------------------------------------------
        # Step 1: Memory & Style Retrieval
        # -------------------------------------------------------------
        prog.notify("Step 1: Memory Retrieval", f"Fetching learned styles for educator '{self.teacher_id}' on category '{category}'...")
        teacher_style = self.preference_learner.get_style_for_category(category)
        retrieved_context = self.rag_retriever.retrieve_context(user_prompt)

        # -------------------------------------------------------------
        # Step 2: Blueprint Proposer
        # -------------------------------------------------------------
        prog.notify("Step 2: Blueprint Proposer", f"Synthesizing learning objectives, question breakdown, and mark distributions...")
        blueprint = self.question_author.propose_blueprint(
            prompt=user_prompt,
            paper_type=paper_type,
            category=category,
            teacher_style=teacher_style,
            retrieved_context=retrieved_context
        )
        blueprint.syllabus_code = syllabus_code
        blueprint.paper_number = paper_number

        # -------------------------------------------------------------
        # Step 3: Tool Execution (Datasets & LaTeX)
        # -------------------------------------------------------------
        prog.notify("Step 3: Tool Execution", "Synthesizing demographic datasets and candidate companion files...")
        companion_dataset = None
        generated_datasets = []
        starter_files = []

        if blueprint.dataset_required or paper_type == "practical":
            companion_dataset = self.dataset_generator.generate_dataset(
                domain_topic=user_prompt,
                record_count=12,
                preferred_format="csv"
            )
            generated_datasets.append({
                "filename": companion_dataset.filename,
                "content": companion_dataset.csv_content
            })
            if companion_dataset.sql_schema_content:
                generated_datasets.append({
                    "filename": "SCHEMA.sql",
                    "content": companion_dataset.sql_schema_content
                })
            if companion_dataset.starter_python_code:
                starter_files.append({
                    "filename": "starter_task.py",
                    "content": companion_dataset.starter_python_code
                })

        prog.notify("Step 3: Tool Execution", "Authoring golden LaTeX question paper and Cambridge mark scheme...")
        latex_paper_source = self.question_author.author_latex_paper(
            blueprint=blueprint,
            companion_dataset=companion_dataset,
            institution=institution,
            exam_year=exam_year,
            exam_series=exam_series
        )

        mark_scheme_source = self.question_author.author_mark_scheme(
            blueprint=blueprint,
            latex_paper_source=latex_paper_source,
            institution=institution,
            exam_year=exam_year,
            exam_series=exam_series
        )

        # -------------------------------------------------------------
        # Step 4: Self-Healing Compilation Sandbox
        # -------------------------------------------------------------
        prog.notify("Step 4: Self-Healing Sandbox", "Executing headless pdflatex compilation in container sandbox...")
        compilation_result = self.latex_compiler.compile(
            latex_source=latex_paper_source,
            working_dir=session_dir,
            job_name="paper"
        )

        if compilation_result.success:
            prog.notify("Step 4: Self-Healing Sandbox", f"Compilation succeeded in {compilation_result.attempts} attempt(s)!")
        else:
            prog.notify("Step 4: Self-Healing Sandbox", f"LaTeX compilation notice: {compilation_result.compilation_log[:150]}...")

        # Also compile mark scheme
        ms_result = self.latex_compiler.compile(
            latex_source=mark_scheme_source,
            working_dir=session_dir,
            job_name="mark_scheme"
        )

        # -------------------------------------------------------------
        # Step 5: Multi-Artefact Bundle & Persistence
        # -------------------------------------------------------------
        prog.notify("Step 5: Packaging & Persistence", "Persisting session state in Firestore and building export archive...")
        session = ExamSession(
            session_id=sess_id,
            title=f"{blueprint.title} ({paper_type.capitalize()})",
            teacher_id=self.teacher_id,
            paper_type=paper_type,
            category=category,
            syllabus_code=syllabus_code,
            paper_number=paper_number,
            institution=institution,
            exam_year=exam_year,
            exam_series=exam_series,
            blueprint=blueprint.model_dump(),
            latex_source=compilation_result.repaired_source or latex_paper_source,
            mark_scheme_source=ms_result.repaired_source or mark_scheme_source,
            generated_datasets=generated_datasets,
            starter_files=starter_files,
            status="completed" if compilation_result.success else "draft",
            compilation_logs=compilation_result.compilation_log,
            pdf_path=str(compilation_result.pdf_path) if compilation_result.pdf_path else None
        )

        self.session_manager.save_session(session)
        prog.notify("Complete", "Exam package generated and ready for inspection/export.")
        return session
