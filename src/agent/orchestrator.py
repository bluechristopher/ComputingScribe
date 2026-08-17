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
from src.generators.document_transcriber import DocumentTranscriber
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
        self.document_transcriber = DocumentTranscriber()
        self.latex_compiler = LaTeXCompiler(max_healing_attempts=3)

        # Pre-seed authentic Cambridge 9569 exemplar grounding
        sample_path = Path(__file__).resolve().parent.parent.parent / "sample" / "practical.txt"
        if sample_path.exists():
            try:
                sample_text = sample_path.read_text(encoding="utf-8")
                self.rag_retriever.add_document({
                    "filename": "Singapore_Cambridge_9569_2025_Paper2_Official.txt",
                    "full_text": sample_text
                })
            except Exception as e:
                print(f"[Orchestrator] Note: Could not auto-seed sample reference: {e}")

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
        institution: str = "HelloWorld Junior College",
        exam_year: str = "2027",
        exam_series: str = "PRELIM",
        progress: Optional[ExamGenerationProgress] = None
    ) -> ExamSession:
        """
        Autonomous 7-Station Pipeline:
        1. Station 1: Memory & Style Agent (Firestore)
        2. Station 2: RAG Grounding Agent (Syllabus 9569 & Exemplars)
        3. Station 3: Blueprint Architect Agent (Gemini 3.7 Flash)
        4. Station 4: Demographic Synthesizer Agent (50/50 Gender Parity Datasets)
        5. Station 5: Golden TeX Authoring Agent (Cambridge LaTeX & Mark Scheme)
        6. Station 6: Self-Healing Sandbox Agent (Headless pdflatex + 3-pass Gemini repair)
        7. Station 7: Artifact Packaging Agent (Firestore Sync & .ZIP Bundling)
        """
        prog = progress or ExamGenerationProgress()
        sess_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        session_dir = LOCAL_SESSIONS_DIR / sess_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # -------------------------------------------------------------
        # Station 1 & 2: Memory & RAG Grounding Agents
        # -------------------------------------------------------------
        prog.notify("Station 1: Memory & Style Agent", f"Querying persistent profile in Firestore for educator '{self.teacher_id}' on category '{category}'...")
        teacher_style = self.preference_learner.get_style_for_category(category)
        
        prog.notify("Station 2: RAG Grounding Agent", f"Scanning syllabus 9569 learning objectives and indexing exemplar past paper structures...")
        retrieved_context = self.rag_retriever.retrieve_context(user_prompt)

        # -------------------------------------------------------------
        # Station 3: Blueprint Architect Agent
        # -------------------------------------------------------------
        prog.notify("Station 3: Blueprint Architect Agent", f"Synthesizing structured learning objectives, task breakdown, and mark distribution with Gemini 3.7 Flash...")
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
        # Station 4: Demographic Synthesizer Agent
        # -------------------------------------------------------------
        prog.notify("Station 4: Demographic Synthesizer Agent", "Synthesizing 50/50 gender balanced candidate datasets & SQL companion files...")
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

        # -------------------------------------------------------------
        # Station 5: Golden TeX Authoring Agent
        # -------------------------------------------------------------
        prog.notify("Station 5: Golden TeX Authoring Agent", "Drafting Cambridge-compliant LaTeX exam paper and granular mark scheme...")
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
        # Station 6: Self-Healing Sandbox Agent
        # -------------------------------------------------------------
        prog.notify("Station 6: Self-Healing Sandbox Agent", "Executing headless pdflatex compilation and 3-pass Gemini self-healing verification...")
        compilation_result = self.latex_compiler.compile(
            latex_source=latex_paper_source,
            working_dir=session_dir,
            job_name="paper"
        )

        # Compile mark scheme as well
        ms_result = self.latex_compiler.compile(
            latex_source=mark_scheme_source,
            working_dir=session_dir,
            job_name="mark_scheme"
        )

        # -------------------------------------------------------------
        # Station 7: Artifact Packaging Agent
        # -------------------------------------------------------------
        prog.notify("Station 7: Artifact Packaging Agent", "Persisting session state in Firestore and building downloadable .zip export bundle...")
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

    def author_single_task(
        self,
        prompt: str,
        paper_type: str = "practical",
        category: str = "sec1_linear_adts",
        task_number: int = 1,
        total_marks: int = 25
    ) -> Dict[str, Any]:
        """Authors a single isolated task/question."""
        teacher_style = self.preference_learner.get_style_for_category(category)
        return self.question_author.author_single_task(
            prompt=prompt,
            paper_type=paper_type,
            category=category,
            task_number=task_number,
            total_marks=total_marks,
            teacher_style=teacher_style
        )

    def refine_single_task(
        self,
        current_task: Dict[str, Any],
        refinement_prompt: str,
        paper_type: str = "practical"
    ) -> Dict[str, Any]:
        """Refines a single task based on conversational feedback."""
        return self.question_author.refine_single_task(
            current_task=current_task,
            refinement_prompt=refinement_prompt,
            paper_type=paper_type
        )

    def renumber_task(
        self,
        task_dict: Dict[str, Any],
        new_number: int,
        paper_type: str = "practical"
    ) -> Dict[str, Any]:
        """Renumbers a single task's macros and labels."""
        return self.question_author.renumber_task(
            task_dict=task_dict,
            new_number=new_number,
            paper_type=paper_type
        )

    def refine_full_paper(
        self,
        session: ExamSession,
        refinement_prompt: str
    ) -> ExamSession:
        """Applies conversational refinement across the entire working exam session."""
        res = self.question_author.refine_full_paper(
            latex_paper_source=session.latex_source,
            mark_scheme_source=session.mark_scheme_source,
            refinement_prompt=refinement_prompt,
            paper_type=session.paper_type
        )
        session.latex_source = res.get("latex_source", session.latex_source)
        session.mark_scheme_source = res.get("mark_scheme_source", session.mark_scheme_source)
        
        session_dir = LOCAL_SESSIONS_DIR / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Recompile PDF with updated changes
        comp_res = self.latex_compiler.compile(
            latex_source=session.latex_source,
            working_dir=session_dir,
            job_name="paper"
        )
        session.pdf_path = str(comp_res.pdf_path) if comp_res.pdf_path else None
        self.session_manager.save_session(session)
        return session

    def compile_assembled_session(
        self,
        tasks_list: List[Dict[str, Any]],
        paper_type: str = "practical",
        syllabus_code: str = "9569",
        paper_number: str = "02",
        institution: str = "HelloWorld Junior College",
        exam_year: str = "2027",
        exam_series: str = "PRELIM",
        session_id: Optional[str] = None
    ) -> ExamSession:
        """Assembles a list of authored tasks into a unified, compilable ExamSession."""
        sess_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        session_dir = LOCAL_SESSIONS_DIR / sess_id
        session_dir.mkdir(parents=True, exist_ok=True)

        assembled = self.question_author.assemble_full_paper(
            tasks_list=tasks_list,
            paper_type=paper_type,
            syllabus_code=syllabus_code,
            paper_number=paper_number,
            institution=institution,
            exam_year=exam_year,
            exam_series=exam_series
        )

        latex_paper_source = assembled["latex_source"]
        mark_scheme_source = assembled["mark_scheme_source"]
        total_marks = assembled["total_marks"]

        # Synthesize companion dataset if practical
        generated_datasets = []
        starter_files = []
        if paper_type == "practical":
            companion_dataset = self.dataset_generator.generate_dataset(
                domain_topic="Practical Assessment Tasks",
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

        # Compile in sandbox
        comp_res = self.latex_compiler.compile(latex_paper_source, session_dir, job_name="paper")
        ms_res = self.latex_compiler.compile(mark_scheme_source, session_dir, job_name="mark_scheme")

        # Build blueprint summary
        blueprint_data = {
            "title": f"Singapore-Cambridge GCE A-Level H2 Computing ({'Paper 2 Practical' if paper_type == 'practical' else 'Paper 1 Written'})",
            "paper_type": paper_type,
            "syllabus_code": syllabus_code,
            "paper_number": paper_number,
            "total_marks": total_marks,
            "learning_objectives": [t.get("title", f"Task {idx+1}") for idx, t in enumerate(tasks_list)],
            "sections": [
                {
                    "number": t.get("task_number", idx + 1),
                    "title": t.get("title", f"Task {idx+1}"),
                    "topic": t.get("topic", "Syllabus Module"),
                    "marks": t.get("marks", 25),
                    "subparts": []
                }
                for idx, t in enumerate(tasks_list)
            ]
        }

        session = ExamSession(
            session_id=sess_id,
            title=f"Assembled H2 Computing {paper_type.capitalize()} Paper ({len(tasks_list)} Tasks)",
            teacher_id=self.teacher_id,
            paper_type=paper_type,
            category="assembled_paper",
            syllabus_code=syllabus_code,
            paper_number=paper_number,
            institution=institution,
            exam_year=exam_year,
            exam_series=exam_series,
            blueprint=blueprint_data,
            latex_source=comp_res.repaired_source or latex_paper_source,
            mark_scheme_source=ms_res.repaired_source or mark_scheme_source,
            generated_datasets=generated_datasets,
            starter_files=starter_files,
            questions=tasks_list,
            status="completed" if comp_res.success else "draft",
            compilation_logs=comp_res.compilation_log,
            pdf_path=str(comp_res.pdf_path) if comp_res.pdf_path else None
        )

        self.session_manager.save_session(session)
        return session

    def transcribe_and_compile_document(
        self,
        file_bytes: bytes,
        filename: str,
        paper_type: str = "auto",
        institution: str = "Singapore Junior College",
        exam_year: str = "2026",
        exam_series: str = "PRELIM",
        syllabus_code: str = "9569",
        paper_number: str = "02",
        session_id: Optional[str] = None,
        progress: Optional[ExamGenerationProgress] = None
    ) -> ExamSession:
        """
        Transcribes an uploaded Word (.docx) or PDF (.pdf) exam document into
        conformed Cambridge LaTeX, compiles it to PDF, and packages a session.
        """
        prog = progress or ExamGenerationProgress()
        sess_id = session_id or f"transcribe_{uuid.uuid4().hex[:8]}"
        session_dir = LOCAL_SESSIONS_DIR / sess_id
        session_dir.mkdir(parents=True, exist_ok=True)

        prog.notify("Station 1: Document Ingestion", f"Extracting structured text & tables from '{filename}'...")
        transcription = self.document_transcriber.transcribe_file_bytes(
            file_bytes=file_bytes,
            filename=filename,
            paper_type=paper_type,
            institution=institution,
            exam_year=exam_year,
            exam_series=exam_series,
            syllabus_code=syllabus_code,
            paper_number=paper_number
        )

        detected_type = transcription["detected_paper_type"]
        latex_source = transcription["latex_source"]
        ms_source = transcription["mark_scheme_source"]
        total_marks = transcription["total_marks"]

        prog.notify("Station 2: Cambridge Conformance", f"Normalized to Cambridge {detected_type.upper()} standard ({total_marks} marks)...")

        prog.notify("Station 3: Compilation Sandbox", "Compiling normalized LaTeX document and mark scheme...")
        comp_res = self.latex_compiler.compile(latex_source, session_dir, job_name="paper")
        ms_res = self.latex_compiler.compile(ms_source, session_dir, job_name="mark_scheme")

        blueprint_data = {
            "title": f"Transcribed Singapore-Cambridge H2 Computing ({'Paper 2 Practical' if detected_type == 'practical' else 'Paper 1 Theory'})",
            "paper_type": detected_type,
            "syllabus_code": syllabus_code,
            "paper_number": paper_number,
            "total_marks": total_marks,
            "learning_objectives": [f"Transcribed from {filename}"],
            "sections": [
                {
                    "number": 1,
                    "title": f"Transcribed Assessment ({filename})",
                    "topic": "Transcribed Exam",
                    "marks": total_marks,
                    "subparts": []
                }
            ]
        }

        session = ExamSession(
            session_id=sess_id,
            title=f"Transcribed Cambridge {detected_type.capitalize()} Paper ({filename})",
            teacher_id=self.teacher_id,
            paper_type=detected_type,
            category="transcribed_paper",
            syllabus_code=syllabus_code,
            paper_number=paper_number,
            institution=institution,
            exam_year=exam_year,
            exam_series=exam_series,
            blueprint=blueprint_data,
            latex_source=comp_res.repaired_source or latex_source,
            mark_scheme_source=ms_res.repaired_source or ms_source,
            generated_datasets=[],
            starter_files=[],
            questions=[{
                "task_number": 1,
                "title": f"Transcribed Task ({filename})",
                "topic": "Transcribed",
                "marks": total_marks,
                "latex_code": transcription["latex_body"],
                "mark_scheme_code": transcription["mark_scheme_body"]
            }],
            status="completed" if comp_res.success else "draft",
            compilation_logs=comp_res.compilation_log,
            pdf_path=str(comp_res.pdf_path) if comp_res.pdf_path else None
        )

        prog.notify("Station 4: Packaging", f"Session saved. Ready for inspection and PDF export.")
        self.session_manager.save_session(session)
        return session
