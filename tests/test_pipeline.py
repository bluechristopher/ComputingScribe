"""
EduScribe AI - Automated Pipeline & Architecture Test Suite
Verifies preference learning, demographic dataset synthesis, LaTeX templating,
session persistence, and end-to-end orchestrator generation for Practical & Theory papers.
"""

import sys
import unittest
from pathlib import Path
import json

# Setup project path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.agent.preference_learner import PreferenceLearner
from src.agent.session_manager import SessionManager, ExamSession
from src.generators.dataset_generator import DatasetGenerator
from src.generators.question_author import QuestionAuthor
from src.sandbox.latex_compiler import LaTeXCompiler
from src.sandbox.code_executor import CodeExecutor
from src.agent.orchestrator import EduScribeOrchestrator

class TestEduScribePipeline(unittest.TestCase):

    def setUp(self):
        self.teacher_id = "test_educator"
        self.session_mgr = SessionManager()
        self.pref_learner = PreferenceLearner(teacher_id=self.teacher_id)
        self.dataset_gen = DatasetGenerator()
        self.question_author = QuestionAuthor()
        self.orchestrator = EduScribeOrchestrator(teacher_id=self.teacher_id)

    def test_1_demographic_fairness_dataset(self):
        """Tests that dataset generator strictly enforces balanced demographics and valid CSV/SQL."""
        dataset = self.dataset_gen.generate_dataset("Candidate Assessment Scores", record_count=10)
        self.assertEqual(dataset.file_type, "csv")
        self.assertTrue(len(dataset.records) >= 10)
        
        # Check gender distribution
        genders = [r["Gender"] for r in dataset.records]
        male_count = genders.count("Male")
        female_count = genders.count("Female")
        self.assertEqual(male_count, female_count, f"Gender balance expected 50/50, got {male_count}:{female_count}")
        
        # Check CSV content non-empty
        self.assertIn("CandidateID", dataset.csv_content)
        self.assertIsNotNone(dataset.sql_schema_content)
        print(" [PASS] Demographic Fairness & Dataset Generation Verified.")

    def test_2_practical_paper_templating(self):
        """Tests practical paper blueprint and LaTeX generation with Cambridge preambles."""
        bp = self.question_author.propose_blueprint(
            prompt="Stack ADT and CSV handling",
            paper_type="practical",
            category="sec1_linear_adts"
        )
        self.assertEqual(bp.paper_type, "practical")
        self.assertEqual(bp.syllabus_code, "9569")
        self.assertTrue(len(bp.sections) >= 1)

        ds = self.dataset_gen.generate_dataset("Stack ADT", record_count=6)
        tex_source = self.question_author.author_latex_paper(
            blueprint=bp,
            companion_dataset=ds,
            institution="HelloWorld Junior College",
            exam_year="2027"
        )
        self.assertIn(r"\documentclass", tex_source)
        self.assertIn("HelloWorld Junior College", tex_source)
        self.assertIn(r"\Marks{", tex_source)
        print(" [PASS] Practical Paper LaTeX Templating Verified.")

    def test_3_theory_paper_templating(self):
        """Tests theory paper blueprint and LaTeX generation with Decision Tables and Pseudocode."""
        bp = self.question_author.propose_blueprint(
            prompt="Decision tables and trace table analysis",
            paper_type="theory",
            category="sec2_logic_decision_tables"
        )
        self.assertEqual(bp.paper_type, "theory")
        self.assertEqual(bp.syllabus_code, "9569")
        
        tex_source = self.question_author.author_latex_paper(
            blueprint=bp,
            companion_dataset=None,
            institution="HelloWorld Junior College",
            exam_year="2027"
        )
        self.assertIn(r"\begin{questions}", tex_source)
        self.assertIn(r"\Marks{", tex_source)
        
        ms_source = self.question_author.author_mark_scheme(
            blueprint=bp,
            latex_paper_source=tex_source,
            institution="HelloWorld Junior College",
            exam_year="2027"
        )
        self.assertIn(r"MARK SCHEME", ms_source)
        print(" [PASS] Theory Paper & Mark Scheme Generation Verified.")

    def test_4_session_lifecycle_and_zip_export(self):
        """Tests session saving, reloading, .zip packaging, and deletion."""
        session_id = "test_unit_session_01"
        sess = ExamSession(
            session_id=session_id,
            title="Unit Test Exam Session",
            teacher_id=self.teacher_id,
            paper_type="practical",
            syllabus_code="9569",
            paper_number="02",
            latex_source=r"\documentclass{article}\begin{document}Test\end{document}",
            mark_scheme_source=r"\documentclass{article}\begin{document}MS\end{document}",
            generated_datasets=[{"filename": "DATA.csv", "content": "A,B\n1,2"}]
        )
        # Save
        self.session_mgr.save_session(sess)
        
        # Load
        loaded = self.session_mgr.get_session(session_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.title, "Unit Test Exam Session")

        # Zip bundle
        zip_bytes = self.session_mgr.export_bundle_zip(session_id)
        self.assertIsNotNone(zip_bytes)
        self.assertTrue(len(zip_bytes) > 50)

        # Cleanup
        self.session_mgr.delete_session(session_id)
        self.assertIsNone(self.session_mgr.get_session(session_id))
        print(" [PASS] Session Lifecycle & .ZIP Export Verified.")

    def test_5_end_to_end_orchestrator(self):
        """Tests complete 5-step orchestrator execution for Practical and Theory workflows."""
        # Practical run
        session_p = self.orchestrator.generate_exam_package(
            user_prompt="Binary search tree traversal and Python file handling",
            paper_type="practical",
            category="sec1_nonlinear_bst_hash",
            syllabus_code="9569",
            paper_number="02",
            exam_year="2027"
        )
        self.assertIsNotNone(session_p)
        self.assertEqual(session_p.paper_type, "practical")
        self.assertEqual(session_p.syllabus_code, "9569")
        self.assertTrue(len(session_p.generated_datasets) > 0)
        
        # Theory run
        session_t = self.orchestrator.generate_exam_package(
            user_prompt="Relational database normalisation 1NF-3NF and SQL queries",
            paper_type="theory",
            category="sec3_sql_normalisation",
            syllabus_code="9569",
            paper_number="01",
            exam_year="2027"
        )
        self.assertIsNotNone(session_t)
        self.assertEqual(session_t.paper_type, "theory")
        self.assertEqual(session_t.syllabus_code, "9569")
        print(" [PASS] End-to-End Orchestrator Verified for Dual Paper Types.")

    def test_6_single_question_studio_and_renumbering(self):
        """Tests single question authoring, conversational refinement, auto-renumbering, and paper assembly."""
        # 1. Author single task
        task_1 = self.orchestrator.author_single_task(
            prompt="Stack ADT implementation in Python",
            paper_type="practical",
            category="sec1_linear_adts",
            task_number=1,
            total_marks=25
        )
        self.assertEqual(task_1["task_number"], 1)
        self.assertIn(r"\maintask{1}", task_1["latex_code"])
        self.assertIn(r"\subtask{1.1}", task_1["latex_code"])

        # 2. Refine single task
        refined = self.orchestrator.refine_single_task(
            current_task=task_1,
            refinement_prompt="Require docstring type annotations",
            paper_type="practical"
        )
        self.assertEqual(refined["task_number"], 1)

        # 3. Renumber task from 3 to 1
        task_3 = self.orchestrator.author_single_task(
            prompt="OOP Class Hierarchy",
            paper_type="practical",
            category="sec3_oop_hierarchies",
            task_number=3,
            total_marks=25
        )
        self.assertIn(r"\maintask{3}", task_3["latex_code"])
        
        renumbered_task = self.orchestrator.renumber_task(task_3, new_number=1, paper_type="practical")
        self.assertEqual(renumbered_task["task_number"], 1)
        self.assertIn(r"\maintask{1}", renumbered_task["latex_code"])
        self.assertIn(r"\subtask{1.1}", renumbered_task["latex_code"])

        # 4. Assemble multiple tasks into unified paper
        tasks_list = [task_1, renumbered_task]
        assembled = self.question_author.assemble_full_paper(
            tasks_list=tasks_list,
            paper_type="practical",
            syllabus_code="9569",
            paper_number="02"
        )
        self.assertIn(r"\documentclass", assembled["latex_source"])
        self.assertEqual(assembled["total_marks"], 50)
        print(" [PASS] Question-by-Question Studio & Auto-Renumbering Verified.")

if __name__ == "__main__":
    unittest.main()

