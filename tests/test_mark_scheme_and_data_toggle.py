import unittest
from pathlib import Path
from src.sandbox.latex_compiler import LaTeXSyntaxValidator, LaTeXCompiler
from src.generators.question_author import ExamBlueprint, QuestionAuthor
from src.agent.orchestrator import EduScribeOrchestrator

class TestMarkSchemeAndDataToggle(unittest.TestCase):
    def setUp(self):
        self.orchestrator = EduScribeOrchestrator(teacher_id="test_ms_user")
        self.qa = QuestionAuthor()

    def test_mark_scheme_syntax_validity(self):
        bp = ExamBlueprint(
            title="Cambridge H2 Computing Prelim",
            syllabus_code="9569",
            paper_number="02",
            paper_type="practical",
            total_marks=25,
            duration="2 hours",
            learning_objectives=["Implement stack ADT"],
            sections=[],
            tasks=[]
        )
        ms_tex = self.qa.author_mark_scheme(
            blueprint=bp,
            latex_paper_source="",
            institution="Test Institution",
            exam_year="2027",
            exam_series="PRELIM"
        )
        
        # Verify template imports enumitem, tabularx, amsmath
        self.assertIn(r"\usepackage{enumitem}", ms_tex)
        self.assertIn(r"\usepackage{tabularx}", ms_tex)
        self.assertIn(r"\begin{tabularx}", ms_tex)
        self.assertIn(r"\end{tabularx}", ms_tex)

        # Validate syntax
        report = LaTeXSyntaxValidator.validate_syntax(ms_tex)
        self.assertTrue(report.is_valid, f"Mark scheme syntax issues: {report.issues}")

    def test_nested_table_stripping_in_assemble(self):
        sample_tabularx = "\\begin{tabularx}{\\linewidth}{|p{2.2cm}|X|c|p{4.8cm}|}\n\\hline\n\\textbf{Question} & \\textbf{Answer} & \\textbf{Marks} & \\textbf{Guidance} \\\\\n\\hline\n\\textbf{Task 1.1} & Stack implementation & \\textbf{12} & 1 mark per valid line \\\\\n\\hline\n\\end{tabularx}"
        tasks = [
            {
                "task_number": 1,
                "title": "Task 1",
                "topic": "sec1_linear_adt",
                "marks": 12,
                "latex_code": r"\maintask{1} Implement push. \Marks{12}",
                "mark_scheme_code": sample_tabularx
            },
            {
                "task_number": 2,
                "topic": "sec2_algo",
                "title": "Task 2",
                "marks": 13,
                "latex_code": r"\maintask{2} Implement pop. \Marks{13}",
                "mark_scheme_code": r"\textbf{Task 2.1} & Pop method & \textbf{13} & 1 mark per check \\ \hline"
            }
        ]
        
        assembled = self.qa.assemble_full_paper(tasks, paper_type="practical")
        ms_tex = assembled["mark_scheme_source"]
        
        # Ensure no nested tabularx
        self.assertEqual(ms_tex.count(r"\begin{tabularx}"), 1, "Expected exactly one tabularx in assembled mark scheme")
        self.assertEqual(ms_tex.count(r"\end{tabularx}"), 1, "Expected exactly one end tabularx in assembled mark scheme")

    def test_generate_data_files_toggle_disabled(self):
        session = self.orchestrator.generate_exam_package(
            user_prompt="Binary search algorithm",
            paper_type="practical",
            category="sec1_linear_adt",
            skip_self_healing=True,
            generate_data_files=False
        )
        self.assertEqual(len(session.generated_datasets), 0)
        self.assertEqual(len(session.starter_files), 0)

    def test_generate_data_files_toggle_enabled(self):
        session = self.orchestrator.generate_exam_package(
            user_prompt="Customer records dataset processing",
            paper_type="practical",
            category="sec1_linear_adt",
            skip_self_healing=True,
            generate_data_files=True
        )
        self.assertGreater(len(session.generated_datasets), 0)

if __name__ == "__main__":
    unittest.main()
