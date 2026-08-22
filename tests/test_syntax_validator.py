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
            self.assertFalse(res.success)
            self.assertIn('raw\\_data.csv', res.repaired_source)
            self.assertIn('[Syntax Verification]: PASSED', res.compilation_log)
            self.assertIn('[pdflatex Verification]: BLOCKED', res.compilation_log)

    def test_dunder_methods_and_verbatim_cleaning(self):
        t = (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "Define \\code{__init__(self, sku, name, weight_kg)} and \\code{__str__} and \\code{__len__(self)}.\n"
            "Also test \\code{__eq__} and \\code{__hash__}.\n"
            "\\begin{verbatim}\n"
            "p\\_laptop = Product('L001', 'Laptop', 2.5)\n"
            "inv.add\\_stock(p\\_laptop, 'LT001')\n"
            "\\end{verbatim}\n"
            "\\fancyfoot[R]{\\textbf{[Turn over}}\n"
            "\\end{document}"
        )
        sanitized, fixes = LaTeXSyntaxValidator.sanitize_and_repair_deterministically(t)
        self.assertIn("\\code{__init__(self, sku, name, weight_kg)}", sanitized)
        self.assertIn("\\code{__str__}", sanitized)
        self.assertIn("\\code{__len__(self)}", sanitized)
        self.assertIn("\\code{__eq__}", sanitized)
        self.assertIn("\\code{__hash__}", sanitized)
        self.assertIn("p_laptop = Product('L001', 'Laptop', 2.5)", sanitized)
        self.assertIn("inv.add_stock(p_laptop, 'LT001')", sanitized)
        self.assertIn("\\textbf{[Turn over}", sanitized)
        self.assertIn("\\usepackage{underscore}", sanitized)

    def test_fragment_sanitization_never_creates_nested_document(self):
        fragment = (
            "\\documentclass{article}\n"
            "\\usepackage{graphicx}\n"
            "\\begin{document}\n"
            "\\item Use \\code{candidate_id}.\n"
            "\\begin{tabular}{|l|c|r|}\n"
            "Long descriptive value & A & 10 \\\\ \n"
            "\\end{tabular}\n"
            "\\end{document}"
        )
        sanitized, _ = LaTeXSyntaxValidator.sanitize_and_repair_deterministically(
            fragment,
            document_mode=False,
        )
        self.assertNotIn("\\documentclass", sanitized)
        self.assertNotIn("\\begin{document}", sanitized)
        self.assertNotIn("\\end{document}", sanitized)
        self.assertIn("\\code{candidate_id}", sanitized)
        self.assertIn("\\begin{tabularx}{\\linewidth}{|X|X|X|}", sanitized)
        self.assertIn("\\end{tabularx}", sanitized)

    def test_unsupported_csv_listing_language_is_made_portable(self):
        source = (
            "\\documentclass{article}\n"
            "\\usepackage{listings}\n"
            "\\begin{document}\n"
            "\\begin{lstlisting}[language=csv]\n"
            "candidate_id,score\n"
            "\\end{lstlisting}\n"
            "\\end{document}"
        )
        sanitized, fixes = LaTeXSyntaxValidator.sanitize_and_repair_deterministically(source)
        self.assertIn("\\begin{lstlisting}[language={}]", sanitized)
        self.assertTrue(any("language=csv" in fix for fix in fixes))

if __name__ == '__main__':
    unittest.main()
