"""
EduScribe AI - LaTeX Compiler & Self-Healing Sandbox Module
Compiles LaTeX source files using pdflatex. Intercepts compiler errors,
repairs broken syntax/macros with Gemini 3.7 Flash, and retries up to 3 times automatically.
Native pdflatex success is the only condition that marks an export as compiled.
"""

import os
import re
import glob
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from config.gcp_config import AppConfig

class LaTeXCompilationResult:
    def __init__(
        self,
        success: bool,
        pdf_bytes: Optional[bytes] = None,
        pdf_path: Optional[Path] = None,
        compilation_log: str = "",
        attempts: int = 1,
        repaired_source: Optional[str] = None
    ):
        self.success = success
        self.pdf_bytes = pdf_bytes
        self.pdf_path = pdf_path
        self.compilation_log = compilation_log
        self.attempts = attempts
        self.repaired_source = repaired_source

class SyntaxValidationReport:
    def __init__(self, is_valid: bool, issues: Optional[list] = None, sanitized_source: str = "", fixes_applied: Optional[list] = None):
        self.is_valid = is_valid
        self.issues = issues or []
        self.sanitized_source = sanitized_source
        self.fixes_applied = fixes_applied or []


class LaTeXSyntaxValidator:
    """
    Robust static syntax validator and deterministic sanitizer for Cambridge LaTeX documents.
    Provides a conservative preflight check. It complements, but never replaces,
    native pdflatex verification.
    """
    @classmethod
    def sanitize_and_repair_deterministically(
        cls,
        latex_source: str,
        document_mode: bool = True,
    ) -> Tuple[str, list]:
        """
        Applies deterministic regex and AST-level repairs for common LaTeX formatting defects:
        1. Fixes unescaped underscores in plain text / variable names outside code listings & math.
        2. Fixes unclosed code listings / environments.
        3. Balances mismatched environments.
        4. Normalizes Cambridge \\Marks{} macros.
        5. Ensures \\ExamImage macro is properly declared if referenced.
        """
        fixes = []
        source = latex_source

        # The LaTeX listings package has no built-in CSV lexer. ``language=csv``
        # therefore fails in pdflatex/Overleaf; a plain listing is portable and
        # preserves every field exactly as supplied.
        source, csv_language_replacements = re.subn(
            r"language\s*=\s*(?:\{\s*csv\s*\}|csv)(?=\s*(?:[,\]]|$))",
            "language={}",
            source,
            flags=re.IGNORECASE,
        )
        if csv_language_replacements:
            fixes.append("Replaced unsupported listings language=csv with a portable plain listing.")

        # Keep a mark bracket with the final line it assesses. Listings require
        # their closing command to remain on its own line, but prose and tables
        # can safely carry the right-aligned mark on that final line.
        def attach_mark_to_previous_line(match: re.Match) -> str:
            previous_line = match.group(1)
            mark = match.group(2)
            if re.search(r"\\end\{(?:lstlisting|verbatim|minted|pseudocode|python)\}\s*$", previous_line):
                return previous_line + "\n" + mark
            return previous_line + " " + mark

        source, detached_mark_replacements = re.subn(
            r"([^\n]+)\n[ \t]*(\\Marks\{[^}]+\})",
            attach_mark_to_previous_line,
            source,
        )
        if detached_mark_replacements:
            fixes.append("Moved detached mark brackets onto the final assessed line where safe.")

        legacy_code_macros = {
            r"\providecommand{\code}[1]{{\ttfamily\upshape\detokenize{#1}}}": r"\providecommand{\code}[1]{{\begingroup\urlstyle{tt}\path{#1}\endgroup}}",
            r"\newcommand{\code}[1]{{\ttfamily\upshape\detokenize{#1}}}": r"\newcommand{\code}[1]{{\begingroup\urlstyle{tt}\path{#1}\endgroup}}",
        }
        replaced_legacy_code_macro = False
        for legacy_code_macro, replacement_code_macro in legacy_code_macros.items():
            if legacy_code_macro in source:
                source = source.replace(legacy_code_macro, replacement_code_macro)
                replaced_legacy_code_macro = True
        unsupported_nolinkurl_macro = r"\urlstyle{tt}\nolinkurl{#1}\endgroup"
        if unsupported_nolinkurl_macro in source:
            source = source.replace(
                unsupported_nolinkurl_macro,
                r"\urlstyle{tt}\path{#1}\endgroup",
            )
            replaced_legacy_code_macro = True
        if replaced_legacy_code_macro:
            if r"\usepackage{xurl}" not in source and r"\usepackage{url}" not in source:
                source = source.replace(
                    r"\begin{document}",
                    r"\IfFileExists{xurl.sty}{\usepackage{xurl}}{\usepackage{url}}" + "\n\\begin{document}",
                    1,
                )
            fixes.append("Updated inline code formatting to wrap long identifiers within the text width.")

        # Question bodies are fragments. Adding document scaffolding to them would
        # create an invalid nested document once the paper template assembles them.
        if not document_mode:
            source = re.sub(r"\\documentclass(?:\[[^\]]*\])?\{[^}]*\}\s*", "", source)
            source = re.sub(r"^\s*\\usepackage(?:\[[^\]]*\])?\{[^}]*\}\s*$", "", source, flags=re.MULTILINE)
            source = source.replace(r"\begin{document}", "").replace(r"\end{document}", "")

            # Model-generated simple tabulars are a common source of margin
            # overflow. Convert only basic l/c/r tables to width-aware tabularx;
            # complex table specifications are preserved untouched.
            def widen_simple_table(match):
                alignment = match.group(1)
                body = match.group(2)
                if not re.fullmatch(r"[|lcr\s]+", alignment):
                    return match.group(0)
                widened = re.sub(r"[lcr]", "X", alignment)
                fixes.append("Converted a simple tabular to tabularx so cells wrap within the text width.")
                return f"\\begin{{tabularx}}{{\\linewidth}}{{{widened}}}{body}\\end{{tabularx}}"

            source = re.sub(
                r"\\begin\{tabular\}\{([^}]*)\}(.*?)\\end\{tabular\}",
                widen_simple_table,
                source,
                flags=re.DOTALL,
            )

        if document_mode:
            if r"\documentclass" not in source:
                source = r"\documentclass[11pt,a4paper]{article}" + "\n" + source
                fixes.append("Added missing \\documentclass declaration.")
            if r"\begin{document}" not in source:
                source = r"\begin{document}" + "\n" + source
                fixes.append("Added missing \\begin{document}.")
            if r"\end{document}" not in source:
                source = source.rstrip() + "\n\\end{document}\n"
                fixes.append("Added missing \\end{document}.")

        # 2. Check \ExamImage macro definition if \ExamImage is used
        if document_mode and r"\ExamImage" in source and r"\newcommand{\ExamImage}" not in source:
            exam_image_macro = r"\newcommand{\ExamImage}[2]{\par\begin{center}\includegraphics[width=#2]{#1}\end{center}\par}"
            if r"\usepackage{graphicx}" in source:
                source = source.replace(r"\usepackage{graphicx}", r"\usepackage{graphicx}" + "\n" + exam_image_macro, 1)
            else:
                source = source.replace(r"\begin{document}", exam_image_macro + "\n\\begin{document}", 1)
            fixes.append("Injected missing \\ExamImage macro definition into preamble.")

        # 3. Ensure \usepackage{underscore} is present in preamble
        if document_mode and r"\usepackage{underscore}" not in source and r"\documentclass" in source:
            source = source.replace(r"\begin{document}", r"\usepackage{underscore}" + "\n\\begin{document}", 1)
            fixes.append("Added \\usepackage{underscore} to preamble.")

        # 4. Fix unescaped underscores outside verbatim/lstlisting and clean backslashes inside verbatim/lstlisting
        lines = source.splitlines()
        in_code_block = False
        repaired_lines = []

        code_env_starts = (r"\begin{lstlisting}", r"\begin{verbatim}", r"\begin{minted}", r"\begin{python}")
        code_env_ends = (r"\end{lstlisting}", r"\end{verbatim}", r"\end{minted}", r"\end{python}")

        for line in lines:
            stripped = line.strip()
            if any(stripped.startswith(start) for start in code_env_starts):
                in_code_block = True
                repaired_lines.append(line)
                continue
            if any(stripped.startswith(end) for end in code_env_ends):
                in_code_block = False
                repaired_lines.append(line)
                continue

            if in_code_block:
                # Inside verbatim/lstlisting: code must be pure Python without LaTeX escapes
                clean_code_line = line.replace(r"\_", "_").replace(r"\%", "%").replace(r"\&", "&").replace(r"\#", "#")
                if clean_code_line != line:
                    fixes.append("Cleaned accidental LaTeX escapes inside verbatim/lstlisting code block.")
                repaired_lines.append(clean_code_line)
                continue

            if stripped.startswith("%") or r"\documentclass" in line or r"\usepackage" in line:
                repaired_lines.append(line)
                continue

            # Fix common macro syntax variations: e.g. \Marks [5] -> \Marks{5}, \Marks 5 -> \Marks{5}
            line = re.sub(r"\\Marks\s*\[\s*(\d+)\s*\]", r"\\Marks{\1}", line)
            line = re.sub(r"\\Marks\s+(\d+)", r"\\Marks{\1}", line)

            # Fix unescaped underscores in plain text words while preserving the
            # literal contents of the template's \code{...} macro.
            parts = re.split(r"(\$[^\$]+\$)", line)
            new_parts = []
            for part in parts:
                if part.startswith("$") and part.endswith("$") and len(part) > 1:
                    new_parts.append(part)
                else:
                    protected_code = []

                    def protect_code(match):
                        protected_code.append(match.group(0))
                        return f"@@CODE{len(protected_code) - 1}@@"

                    protected_part = re.sub(r"\\code\{[^{}]*\}", protect_code, part)
                    subbed = re.sub(r"(?<!\\)_", r"\_", protected_part)
                    for index, code in enumerate(protected_code):
                        subbed = subbed.replace(f"@@CODE{index}@@", code)
                    new_parts.append(subbed)
            repaired_line = "".join(new_parts)
            if repaired_line != line:
                fixes.append("Escaped unescaped underscore (_) outside math/code.")
            repaired_lines.append(repaired_line)

        source = "\n".join(repaired_lines)

        # Balance only surplus opening braces outside literal code and comments.
        # Appending the missing closers immediately before \end{document} repairs
        # the common truncated-model-output case without touching valid commands.
        brace_source = re.sub(
            r"\\begin\{(verbatim|lstlisting|minted|python)\}.*?\\end\{\1\}",
            "",
            source,
            flags=re.DOTALL,
        )
        brace_source = "\n".join(line.split("%", 1)[0] for line in brace_source.splitlines())
        brace_source = brace_source.replace(r"\{", "").replace(r"\}", "")
        missing_closers = brace_source.count("{") - brace_source.count("}")
        if missing_closers > 0:
            closers = "}" * missing_closers
            if document_mode and r"\end{document}" in source:
                source = source.replace(r"\end{document}", closers + "\n\\end{document}", 1)
            else:
                source = source.rstrip() + closers + "\n"
            fixes.append(f"Added {missing_closers} missing closing brace(s).")

        # 5. Check and balance environments
        env_stack = []
        unclosed_envs = []
        env_pattern = re.compile(r"\\(begin|end)\{([a-zA-Z0-9\*]+)\}")
        for match in env_pattern.finditer(source):
            action, env_name = match.groups()
            if env_name == "document":
                continue
            if action == "begin":
                env_stack.append(env_name)
            elif action == "end":
                if env_stack and env_stack[-1] == env_name:
                    env_stack.pop()
                elif env_name in env_stack:
                    while env_stack and env_stack[-1] != env_name:
                        unclosed = env_stack.pop()
                        unclosed_envs.append(unclosed)
                    if env_stack:
                        env_stack.pop()

        # Any remaining environments on stack are unclosed before \end{document}
        unclosed_envs.extend(reversed(env_stack))
        if unclosed_envs:
            closing_tags = "\n".join([f"\\end{{{e}}}" for e in unclosed_envs])
            if document_mode and r"\end{document}" in source:
                source = source.replace(r"\end{document}", f"{closing_tags}\n\\end{{document}}")
            else:
                source = source.rstrip() + f"\n{closing_tags}\n"
            fixes.append(f"Auto-closed unclosed environments: {', '.join(unclosed_envs)}.")

        return source, list(set(fixes))

    @classmethod
    def validate_syntax(cls, latex_source: str) -> SyntaxValidationReport:
        """
        Validates the syntactic integrity of a LaTeX document.
        Returns a detailed SyntaxValidationReport.
        """
        issues = []
        # Literal code/output environments do not interpret braces, dollars, or
        # LaTeX commands. Mask their contents before performing TeX checks.
        syntax_source = re.sub(
            r"\\begin\{(verbatim|lstlisting|minted|python)\}.*?\\end\{\1\}",
            lambda match: f"\\begin{{{match.group(1)}}}\\end{{{match.group(1)}}}",
            latex_source,
            flags=re.DOTALL,
        )
        
        # 1. Environment Balance Check
        env_stack = []
        env_pattern = re.compile(r"\\(begin|end)\{([a-zA-Z0-9\*]+)\}")
        for match in env_pattern.finditer(syntax_source):
            action, env_name = match.groups()
            if action == "begin":
                env_stack.append(env_name)
            elif action == "end":
                if not env_stack:
                    issues.append(f"Unexpected \\end{{{env_name}}} without matching \\begin{{{env_name}}}")
                elif env_stack[-1] != env_name:
                    issues.append(f"Mismatched environment: expected \\end{{{env_stack[-1]}}}, found \\end{{{env_name}}}")
                    if env_name in env_stack:
                        while env_stack and env_stack[-1] != env_name:
                            env_stack.pop()
                        if env_stack:
                            env_stack.pop()
                else:
                    env_stack.pop()

        if env_stack:
            unclosed = [e for e in env_stack if e != "document"]
            if unclosed:
                issues.append(f"Unclosed environments: {', '.join(unclosed)}")

        # 2. Curly Brace Balance Check (ignoring \{ and \})
        sanitized_no_escapes = syntax_source.replace(r"\{", "").replace(r"\}", "")
        lines = [line.split("%")[0] for line in sanitized_no_escapes.splitlines()]
        code_without_comments = "\n".join(lines)
        open_braces = code_without_comments.count("{")
        close_braces = code_without_comments.count("}")
        if open_braces != close_braces:
            issues.append(f"Unbalanced curly braces: {open_braces} open '{{' vs {close_braces} close '}}'")

        # 3. Math Mode Delimiter Check
        no_escaped_dollars = syntax_source.replace(r"\$", "")
        dollar_count = 0
        for line in no_escaped_dollars.splitlines():
            clean_line = line.split("%")[0]
            dollar_count += clean_line.count("$")
        if dollar_count % 2 != 0:
            issues.append(f"Unmatched math mode '$' delimiter ({dollar_count} total dollar signs)")

        # 4. Mandatory Structure Check
        if syntax_source.count(r"\documentclass") != 1:
            issues.append("Expected exactly one \\documentclass declaration")
        if r"\documentclass" not in syntax_source:
            issues.append("Missing \\documentclass declaration")
        if syntax_source.count(r"\begin{document}") != 1:
            issues.append("Expected exactly one \\begin{document}")
        if r"\begin{document}" not in syntax_source:
            issues.append("Missing \\begin{document}")
        if syntax_source.count(r"\end{document}") != 1:
            issues.append("Expected exactly one \\end{document}")
        if r"\end{document}" not in syntax_source:
            issues.append("Missing \\end{document}")

        is_valid = len(issues) == 0
        return SyntaxValidationReport(
            is_valid=is_valid,
            issues=issues,
            sanitized_source=latex_source
        )


class LaTeXCompiler:
    def __init__(self, max_healing_attempts: int = 3):
        self.max_healing_attempts = max_healing_attempts
        self.pdflatex_cmd = self._find_pdflatex_executable()

    def _find_pdflatex_executable(self) -> Optional[str]:
        """Locates pdflatex on system PATH or common Windows / Linux installation directories."""
        cmd = shutil.which("pdflatex")
        if cmd:
            return cmd

        candidate_paths = [
            os.path.expanduser(r"~\AppData\Local\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe"),
            r"C:\Program Files\MiKTeX\miktex\bin\x64\pdflatex.exe",
            r"C:\Program Files (x86)\MiKTeX\miktex\bin\pdflatex.exe",
            r"C:\Program Files\MiKTeX\miktex\bin\pdflatex.exe",
        ]
        candidate_paths.extend(glob.glob(r"C:\texlive\*\bin\windows\pdflatex.exe"))
        candidate_paths.extend(glob.glob(r"C:\texlive\*\bin\win32\pdflatex.exe"))

        for p in candidate_paths:
            if os.path.isfile(p):
                return p

        return None

    def _extract_error_snippet(self, log_content: str) -> str:
        """Extracts critical error lines starting with '!' and following context from LaTeX log."""
        lines = log_content.splitlines()
        error_blocks = []
        for i, line in enumerate(lines):
            if line.startswith("!"):
                snippet = "\n".join(lines[max(0, i-2):min(len(lines), i+10)])
                error_blocks.append(snippet)
        
        if error_blocks:
            return "\n---\n".join(error_blocks[:3])
        return "\n".join(lines[-30:]) if lines else "Unknown compilation error"

    def _heal_latex_source(self, broken_source: str, error_log: str) -> str:
        """Invokes Gemini 3.7 Flash to diagnose and repair broken LaTeX syntax or unescaped characters."""
        prompt = rf"""
You are an expert TeX/LaTeX debugging compiler agent.
The following LaTeX document failed syntax validation or pdflatex compilation.

ERROR LOG / SYNTAX AUDIT REPORT:
{error_log}

FULL BROKEN LATEX SOURCE:
{broken_source}

INSTRUCTIONS:
1. Identify and fix the exact syntax error (e.g. unescaped _, %, #, &, missing \end{{...}}, invalid macro, mismatched brackets, or missing package).
2. Strictly preserve all Cambridge exam structure, questions, mark scheme tables, and commands with 100% pedagogical fidelity.
3. Output ONLY the repaired complete LaTeX source code. Do NOT wrap in markdown backticks or commentary.
"""
        client = AppConfig.get_gemini_client()
        if client and hasattr(client, "GenerativeModel"):
            try:
                model = client.GenerativeModel(AppConfig.DEFAULT_MODEL)
                response = model.generate_content(prompt)
                if response and hasattr(response, "text") and response.text:
                    repaired = response.text.replace("```latex", "").replace("```", "").strip()
                    if len(repaired) > 50 and ("\\documentclass" in repaired or "\\begin{document}" in repaired):
                        return repaired
            except Exception as e:
                print(f"[LaTeXCompiler] Gemini self-healing note: {e}")

        # Basic deterministic fallback repair
        healed, _ = LaTeXSyntaxValidator.sanitize_and_repair_deterministically(broken_source)
        return healed

    def compile(
        self,
        latex_source: str,
        working_dir: Path,
        job_name: str = "paper",
        skip_self_healing: bool = False
    ) -> LaTeXCompilationResult:
        """
        Runs deterministic normalization followed by native pdflatex verification.
        A static preflight is useful feedback, but never a substitute for a successful
        compiler run: without pdflatex this method returns ``success=False``.
        """
        working_dir.mkdir(parents=True, exist_ok=True)
        logs_accumulated = []

        # 1. Deterministic Sanitization Pass
        current_source, initial_fixes = LaTeXSyntaxValidator.sanitize_and_repair_deterministically(latex_source)
        if initial_fixes:
            logs_accumulated.append(f"[Deterministic Sanitization]: Applied {len(initial_fixes)} fix(es): {', '.join(initial_fixes)}")

        # 2. Syntax Validation Pass
        syntax_report = LaTeXSyntaxValidator.validate_syntax(current_source)
        if not syntax_report.is_valid:
            logs_accumulated.append(f"[Syntax Validation Issues Detected]: {'; '.join(syntax_report.issues)}")
            # Always heal syntax errors with Gemini if present
            current_source = self._heal_latex_source(current_source, "\n".join(syntax_report.issues))
            # Re-verify after healing
            current_source, _ = LaTeXSyntaxValidator.sanitize_and_repair_deterministically(current_source)
            syntax_report = LaTeXSyntaxValidator.validate_syntax(current_source)
            if syntax_report.is_valid:
                logs_accumulated.append("[Syntax Verification]: Successfully resolved all syntax issues via Gemini reflection.")
            else:
                logs_accumulated.append(f"[Syntax Verification Note]: Remaining minor issues: {'; '.join(syntax_report.issues)}")
        else:
            logs_accumulated.append("[Syntax Verification]: PASSED (0 syntax errors).")

        # 3. Always save verified .tex source to disk
        tex_file = working_dir / f"{job_name}.tex"
        with open(tex_file, "w", encoding="utf-8") as f:
            f.write(current_source)

        # A browser/static preview is not evidence that the export compiles. Keep the
        # source available for repair, but never label it as a compiled artifact.
        if not self.pdflatex_cmd:
            logs_accumulated.append(
                "[pdflatex Verification]: BLOCKED. pdflatex is unavailable; "
                "static validation is not a successful compilation."
            )

            return LaTeXCompilationResult(
                success=False,
                pdf_bytes=None,
                pdf_path=None,
                compilation_log="\n".join(logs_accumulated),
                attempts=1,
                repaired_source=current_source
            )

        # pdflatex is available -> Execute sandbox compilation with auto-repair.
        effective_max_attempts = 1 if skip_self_healing else self.max_healing_attempts

        for attempt in range(1, effective_max_attempts + 1):
            pdf_file = working_dir / f"{job_name}.pdf"
            log_file = working_dir / f"{job_name}.log"

            with open(tex_file, "w", encoding="utf-8") as f:
                f.write(current_source)

            cmd = [
                self.pdflatex_cmd,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                "-no-shell-escape",
                f"-jobname={job_name}",
                tex_file.name
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=working_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=12
                )
            except subprocess.TimeoutExpired:
                print(f"[LaTeXCompiler] pdflatex timed out on attempt {attempt}")
                logs_accumulated.append("[pdflatex Verification]: BLOCKED. Native pdflatex compilation timed out.")
                return LaTeXCompilationResult(
                    success=False,
                    pdf_bytes=None,
                    pdf_path=None,
                    compilation_log="\n".join(logs_accumulated),
                    attempts=attempt,
                    repaired_source=current_source
                )

            log_content = ""
            if log_file.exists():
                with open(log_file, "r", encoding="utf-8", errors="ignore") as lf:
                    log_content = lf.read()

            logs_accumulated.append(f"--- pdflatex Attempt {attempt} ---\n{proc.stdout}\n{proc.stderr}")

            if proc.returncode == 0 and pdf_file.exists():
                # A second pass resolves cross references and labels generated by the
                # first pass. Both runs must succeed for a verified export.
                try:
                    verification_proc = subprocess.run(
                        cmd,
                        cwd=working_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=12,
                    )
                except subprocess.TimeoutExpired:
                    logs_accumulated.append("[pdflatex Verification]: BLOCKED. Second pdflatex pass timed out.")
                    return LaTeXCompilationResult(False, compilation_log="\n".join(logs_accumulated), attempts=attempt, repaired_source=current_source)

                logs_accumulated.append(
                    f"--- pdflatex Verification Pass ---\n{verification_proc.stdout}\n{verification_proc.stderr}"
                )
                if verification_proc.returncode == 0 and pdf_file.exists():
                    pdf_bytes = pdf_file.read_bytes()
                    logs_accumulated.append("[pdflatex Engine]: Native pdflatex compilation succeeded on two passes.")
                    return LaTeXCompilationResult(
                        success=True,
                        pdf_bytes=pdf_bytes,
                        pdf_path=pdf_file,
                        compilation_log="\n".join(logs_accumulated),
                        attempts=attempt,
                        repaired_source=current_source
                    )

                log_content = log_file.read_text(encoding="utf-8", errors="ignore") if log_file.exists() else verification_proc.stdout
                error_snippet = self._extract_error_snippet(log_content)
                logs_accumulated.append(f"[pdflatex Error on verification pass]:\n{error_snippet}")
                if not skip_self_healing and attempt < effective_max_attempts:
                    current_source = self._heal_latex_source(current_source, error_snippet)
                    current_source, _ = LaTeXSyntaxValidator.sanitize_and_repair_deterministically(current_source)
                continue

            # Compilation failed -> extract exact error lines
            error_snippet = self._extract_error_snippet(log_content or proc.stdout)
            logs_accumulated.append(f"[pdflatex Error on Attempt {attempt}]:\n{error_snippet}")

            if not skip_self_healing and attempt < effective_max_attempts:
                logs_accumulated.append(f"[Self-Healing Triggered on Attempt {attempt}]")
                current_source = self._heal_latex_source(current_source, error_snippet)
                current_source, _ = LaTeXSyntaxValidator.sanitize_and_repair_deterministically(current_source)

        return LaTeXCompilationResult(
            success=False,
            pdf_bytes=None,
            pdf_path=None,
            compilation_log="\n".join(logs_accumulated),
            attempts=effective_max_attempts,
            repaired_source=current_source
        )

    def _generate_fallback_pdf(self, latex_content: str, working_dir: Path, job_name: str) -> Path:
        """Generates a structured, publication-grade Cambridge PDF document using FPDF2."""
        out_pdf = working_dir / f"{job_name}.pdf"
        try:
            from fpdf import FPDF
            
            class CambridgeExamPDF(FPDF):
                def header(self):
                    self.set_font("helvetica", "B", 9)
                    self.set_text_color(100, 116, 139)
                    self.cell(0, 8, "SINGAPORE-CAMBRIDGE GCE A-LEVEL H2 COMPUTING (9569)", border=0, align="L")
                    self.cell(0, 8, f"Page {self.page_no()}", border=0, align="R", new_x="LMARGIN", new_y="NEXT")
                    self.set_draw_color(203, 213, 225)
                    self.line(15, 18, 195, 18)
                    self.ln(6)

                def footer(self):
                    self.set_y(-18)
                    self.set_draw_color(203, 213, 225)
                    self.line(15, 279, 195, 279)
                    self.set_font("helvetica", "", 8)
                    self.set_text_color(100, 116, 139)
                    self.cell(0, 8, " (C) HelloWorld Junior College / Cambridge 9569", border=0, align="L")
                    self.cell(0, 8, "9569/PRELIM/2027  [Turn over", border=0, align="R")

            pdf = CambridgeExamPDF(orientation="P", unit="mm", format="A4")
            pdf.set_margins(15, 15, 15)
            pdf.set_auto_page_break(auto=True, margin=22)
            pdf.add_page()
            
            # Title Banner
            pdf.set_font("helvetica", "B", 14)
            pdf.set_text_color(15, 23, 42)
            if "mark_scheme" in job_name.lower():
                pdf.cell(0, 9, "CAMBRIDGE INTERNATIONAL EXAMINATIONS - MARK SCHEME", new_x="LMARGIN", new_y="NEXT", align="C")
                pdf.set_font("helvetica", "B", 11)
                pdf.set_text_color(71, 85, 105)
                pdf.cell(0, 7, "H2 COMPUTING 9569 (MAXIMUM RAW MARK: 100)", new_x="LMARGIN", new_y="NEXT", align="C")
            else:
                pdf.cell(0, 9, "H2 COMPUTING 9569 EXAMINATION PAPER", new_x="LMARGIN", new_y="NEXT", align="C")
                pdf.set_font("helvetica", "B", 11)
                pdf.set_text_color(71, 85, 105)
                pdf.cell(0, 7, "Paper 2 Practical / Paper 1 Written Examination", new_x="LMARGIN", new_y="NEXT", align="C")
            
            pdf.ln(4)

            # Clean LaTeX markup for structured visual rendering
            lines = latex_content.splitlines()
            for raw_line in lines:
                line = raw_line.strip()
                if not line or line.startswith("%") or line.startswith("\\documentclass") or line.startswith("\\usepackage") or line.startswith("\\begin{document}") or line.startswith("\\end{document}"):
                    continue
                
                # Check for Task Header
                if "\\maintask{" in line:
                    task_num = re.search(r"\\maintask\{([^}]+)\}", line)
                    t_val = task_num.group(1) if task_num else ""
                    pdf.ln(3)
                    pdf.set_fill_color(241, 245, 249)
                    pdf.set_font("helvetica", "B", 12)
                    pdf.set_text_color(15, 23, 42)
                    pdf.cell(0, 8, f"  Task {t_val}", new_x="LMARGIN", new_y="NEXT", fill=True)
                    pdf.ln(2)
                    continue

                if "\\subtask{" in line:
                    sub_num = re.search(r"\\subtask\{([^}]+)\}", line)
                    s_val = sub_num.group(1) if sub_num else ""
                    pdf.ln(2)
                    pdf.set_font("helvetica", "B", 10.5)
                    pdf.set_text_color(30, 41, 59)
                    pdf.cell(0, 7, f"Task {s_val}", new_x="LMARGIN", new_y="NEXT")
                    continue

                # Check for Marks
                marks_str = ""
                if "\\Marks{" in line:
                    m_match = re.search(r"\\Marks\{([^}]+)\}", line)
                    if m_match:
                        marks_str = f" [{m_match.group(1)}]"
                    line = re.sub(r"\\Marks\{[^}]+\}", "", line)

                # Clean TeX macros
                clean_text = re.sub(r"\\code\{([^}]+)\}", r"'\1'", line)
                clean_text = re.sub(r"\\textbf\{([^}]+)\}", r"\1", clean_text)
                clean_text = re.sub(r"\\textit\{([^}]+)\}", r"\1", clean_text)
                clean_text = re.sub(r"\\jupytercell\{[^}]*\}\{([^}]*)\}", r"[Code Cell: \1]", clean_text)
                clean_text = re.sub(r"\\[a-zA-Z]+(\[[^\]]*\])?(\{([^}]*)\})?", r" \3 ", clean_text)
                clean_text = re.sub(r"[\{\}\$\%\\]", "", clean_text).strip()

                if clean_text:
                    full_line_text = clean_text + marks_str
                    safe_text = full_line_text.encode('latin-1', 'replace').decode('latin-1')
                    
                    pdf.set_font("helvetica", "", 10)
                    pdf.set_text_color(30, 41, 59)
                    pdf.multi_cell(0, 5.5, safe_text)
                    pdf.ln(1)

            pdf.output(str(out_pdf))
            return out_pdf
        except Exception as e:
            print(f"[LaTeXCompiler] PDF creation notice: {e}")
            return out_pdf
