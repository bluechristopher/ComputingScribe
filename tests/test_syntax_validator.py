import unittest
from pathlib import Path
import tempfile
from src.sandbox.latex_compiler import LaTeXSyntaxValidator, LaTeXCompiler

class TestLaTeXSyntaxValidator(unittest.TestCase):
    def test_unescaped_underscore_sanitization(self):
        t = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "The file candidate_records_2027.csv contains user_id.\n"
            "Math equation: $x_1 + x_2 = 10$.\n"
            "\\Marks [5]\n"
            "\\end{document}"
        )
        sanitized, fixes = LaTeXSyntaxValidator.sanitize_and_repair_deterministically(t)
        self.assertIn("candidate\\_records\\_2027.csv", sanitized)
        self.assertIn("user\\_id", sanitized)
        self.assertIn("$x_1 + x_2 = 10$", sanitized)
        self.assertIn("\\Marks{5}", sanitized)

        report = LaTeXSyntaxValidator.validate_syntax(sanitized)
        self.assertTrue(report.is_valid, f"Issues: {report.issues}")

    def test_unclosed_environments_auto_repair(self):
        t = (
            '\\begin{document}\n'
            '\\begin{enumerate}\n'
            '\\item Question item 1\n'
        )
        sanitized, fixes = LaTeXSyntaxValidator.sanitize_and_repair_deterministically(t)
        self.assertIn('\\documentclass', sanitized)
        self.assertIn('\\end{enumerate}', sanitized)
        self.assertIn('\\end{document}', sanitized)

        report = LaTeXSyntaxValidator.validate_syntax(sanitized)
        self.assertTrue(report.is_valid, f'Issues: {report.issues}')

    def test_unconditional_compiler_syntax_verification(self):
        t = (
            '\\documentclass{article}\n'
            '\\begin{document}\n'
            'File raw_data.csv has records.\n'
            '\\end{document}'
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            compiler = LaTeXCompiler()
            res = compiler.compile(t, Path(tmpdir), job_name='test_paper', skip_self_healing=True)
            self.assertTrue(res.success)
            self.assertIn('raw\\_data.csv', res.repaired_source)
            self.assertIn('[Syntax Verification]: PASSED', res.compilation_log)

if __name__ == '__main__':
    unittest.main()
