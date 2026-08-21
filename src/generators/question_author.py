"""
EduScribe AI - Question Author Module
Specialised authoring engine for Cambridge Practical & Theory exam papers and matching Mark Schemes.
"""

import re
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from config.gcp_config import AppConfig

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

class ExamBlueprint(BaseModel):
    title: str
    paper_type: str = Field(description="'practical' or 'theory'")
    syllabus_code: str = "9569"
    paper_number: str = "02"
    total_marks: int = 100
    learning_objectives: List[str]
    sections: List[Dict[str, Any]]
    dataset_required: bool = True
    dataset_description: Optional[str] = None

class QuestionAuthor:
    def __init__(self):
        pass

    @staticmethod
    def _normalize_marks_spacing(latex_source: str) -> str:
        """Keep mark brackets in the same paragraph as the final question text."""
        latex_source = re.sub(r"[ \t]*\\\\[ \t]*\n[ \t]*(\\Marks\{)", r" \1", latex_source)
        latex_source = re.sub(r"\n[ \t]*\n[ \t]*(\\Marks\{)", r" \1", latex_source)
        latex_source = re.sub(r"([^\n])\n[ \t]*(\\Marks\{)", r"\1 \2", latex_source)
        return latex_source

    def propose_blueprint(
        self,
        prompt: str,
        paper_type: str = "practical",
        category: str = "sec1_linear_adts",
        teacher_style: Optional[Dict[str, Any]] = None,
        retrieved_context: str = ""
    ) -> ExamBlueprint:
        """
        Synthesizes an exam blueprint (objectives, mark distribution, tasks) for H2 Computing 2027 (9569).
        Practical Paper 2: 94 marks for questions + 6 marks for Programming Style & Quality (100 total).
        Theory Paper 1: 100 marks total.
        """
        teacher_style = teacher_style or {}
        is_contextual = "contextual" in prompt.lower() or teacher_style.get("preferred_depth") == "long_contextual"
        preferred_depth = "long_contextual" if is_contextual else teacher_style.get("preferred_depth", "long_contextual")
        
        # 94 marks for Practical (6 marks code style), 100 marks for Theory
        default_paper_marks = 94 if paper_type == "practical" else 100
        target_marks = teacher_style.get("total_marks", default_paper_marks)
        if paper_type == "practical" and target_marks == 100:
            target_marks = 94 # Enforce 94 question marks standard
            
        task_count = teacher_style.get("task_count", 4 if paper_type == "practical" else 5)

        contextual_instructions = """
CONTEXTUAL DEPTH DIRECTIVES (ACTIVE):
- For PRACTICAL (Paper 2):
  * Create an EXTENDED, REAL-WORLD SCENARIO (e.g. Singapore MRT Automated Fare Collection, Hospital Emergency Triage Queue, E-Commerce Warehouse Logistics, or Bank Transaction Ledger).
  * Structure every subtask with CLEAR, STEP-BY-STEP BULLETED POINT INSTRUCTIONS.
  * Explicitly specify data types, method signatures, return values, exception handling, and expected console/Jupyter outputs.
  * Include realistic sample records and structured test tables.
  * TOTAL QUESTION MARKS MUST SUM TO EXACTLY 94 MARKS (6 marks are reserved for Programming Style).

- For THEORY (Paper 1):
  * Develop a RICH, MULTI-PARAGRAPH DOMAIN SCENARIO establishing entities, business rules, hardware/network architecture, and security constraints.
  * All question parts must tie directly into the scenario (e.g. applying 1NF-3NF normalisation to the scenario's functional dependencies, constructing trace tables for scenario algorithms, calculating subnets for the scenario branch offices, or evaluating PDPA/AI ethics for scenario data handling).
  * TOTAL QUESTION MARKS MUST SUM TO EXACTLY 100 MARKS.
""" if is_contextual else ""

        system_instruction = f"""
You are a Principal Examiner for Singapore-Cambridge GCE A-Level H2 Computing (Syllabus 9569 / 2027 examination standards).
Design a structured exam paper blueprint based on the user's prompt and H2 Computing 9569 syllabus standards:

SYLLABUS CORE SECTIONS (H2 Computing 2027):
- Section 1: Data and Data Structures (Arrays, Stacks, Circular Queues, Linked Lists, Binary Search Trees, Hash Tables, Dictionaries)
- Section 2: Algorithms & Problem Solving (Searching, Sorting: Quick/Merge/Insertion/Bubble, Recursion, Decision Tables, Trace Tables, Big-O Complexity)
- Section 3: System Design & Implementation (Python 3, OOP Encapsulation/Inheritance/Polymorphism, ER Modeling, 1NF-3NF Normalisation, SQL DDL/DML, Web Apps/Flask/HTTP, Networks OSI/TCP-IP/Subnetting, Cryptography/SSL/Signatures)
- Section 4: Ethics, Legislation & Emerging Tech (PDPA, IP/Copyright, AI/ML Ethics, Cybersecurity)

Paper Selection: {paper_type.upper()} ({('Paper 2 Practical (9569/02)' if paper_type == 'practical' else 'Paper 1 Theory (9569/01)')})
Category: {category}
Target Total Question Marks: {target_marks} {('(Note: 94 marks for questions + 6 marks Programming Style = 100)' if paper_type == 'practical' else '')}
Expected Tasks/Questions: {task_count}
Educator Preference: {preferred_depth}

User Prompt: {prompt}
{contextual_instructions}
Reference Syllabus Context: {retrieved_context}

Return a valid JSON object matching this schema:
{{
  "title": "Singapore-Cambridge GCE A-Level H2 Computing ({'Paper 2 Practical' if paper_type == 'practical' else 'Paper 1 Written'})",
  "paper_type": "{paper_type}",
  "syllabus_code": "9569",
  "paper_number": "{'02' if paper_type == 'practical' else '01'}",
  "total_marks": {target_marks},
  "learning_objectives": [
    "Design and implement ADTs in Python",
    "Process structured CSV datasets and generate reports",
    "Analyze algorithmic complexity and evaluate Big-O efficiency"
  ],
  "sections": [
    {{
      "number": 1,
      "title": "Task 1: Linear Abstract Data Types (Stack & Queue)",
      "topic": "Section 1: Data and Data Structures",
      "marks": 25,
      "subparts": [
        {{"label": "Task 1.1", "description": "Implement push() and bounds check", "marks": 6}},
        {{"label": "Task 1.2", "description": "Implement pop() with underflow validation", "marks": 6}},
        {{"label": "Task 1.3", "description": "Driver program and boundary test execution", "marks": 13}}
      ]
    }}
  ],
  "dataset_required": true if practical else false,
  "dataset_description": "CANDIDATES.csv file containing candidate assessment data"
}}
"""
        client = AppConfig.get_gemini_client()
        if client and hasattr(client, "GenerativeModel"):
            try:
                model = client.GenerativeModel(AppConfig.DEFAULT_MODEL)
                response = model.generate_content(
                    system_instruction,
                    generation_config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                return ExamBlueprint(**data)
            except Exception as e:
                print(f"[QuestionAuthor] Blueprint generation with Gemini failed/skipped: {e}")

        # Fallback blueprint
        return self._generate_fallback_blueprint(prompt, paper_type, target_marks)

    def _generate_fallback_blueprint(self, prompt: str, paper_type: str, total_marks: int) -> ExamBlueprint:
        if paper_type == "practical":
            return ExamBlueprint(
                title="H2 Computing Practical Examination (Paper 2 / 9569)",
                paper_type="practical",
                syllabus_code="9569",
                paper_number="02",
                total_marks=total_marks,
                learning_objectives=[
                    "Implement Linear & Non-Linear ADTs in Python (Stacks, Queues, Linked Lists, BST)",
                    "Perform CSV/JSON file stream processing and validation",
                    "Design OOP class hierarchies with encapsulation and inheritance",
                    "Implement divide-and-conquer sorting (Quicksort/Merge sort) and recursive searching"
                ],
                sections=[
                    {
                        "number": 1,
                        "title": "Task 1: Abstract Data Types & Pointer Management",
                        "topic": "Section 1: Data and Data Structures (Stack / Circular Queue)",
                        "marks": 25,
                        "subparts": [
                            {"label": "Task 1.1", "description": "Implement push() / enqueue() method with bounds checking", "marks": 6},
                            {"label": "Task 1.2", "description": "Implement pop() / dequeue() with underflow handling", "marks": 6},
                            {"label": "Task 1.3", "description": "Write driver execution code and test cases", "marks": 13}
                        ]
                    },
                    {
                        "number": 2,
                        "title": "Task 2: Structured Dataset Processing and File I/O",
                        "topic": "Section 3: System Design & Implementation (CSV File Processing)",
                        "marks": 25,
                        "subparts": [
                            {"label": "Task 2.1", "description": "Read CANDIDATES.csv into structured dictionaries", "marks": 8},
                            {"label": "Task 2.2", "description": "Filter and aggregate candidate cohort statistics", "marks": 10},
                            {"label": "Task 2.3", "description": "Output distinction summary report to formatted text file", "marks": 7}
                        ]
                    },
                    {
                        "number": 3,
                        "title": "Task 3: Object-Oriented Programming & Hierarchy",
                        "topic": "Section 3: System Design & Implementation (OOP & Polymorphism)",
                        "marks": 20,
                        "subparts": [
                            {"label": "Task 3.1", "description": "Define superclass AssessmentItem with constructor and getters", "marks": 6},
                            {"label": "Task 3.2", "description": "Define subclass PracticalAssessment overriding calculateScore()", "marks": 8},
                            {"label": "Task 3.3", "description": "Instantiate polymorphically and verify method dispatch", "marks": 6}
                        ]
                    },
                    {
                        "number": 4,
                        "title": "Task 4: Sorting, Searching & Algorithm Efficiency",
                        "topic": "Section 2: Algorithms & Complexity (Quicksort / Binary Search)",
                        "marks": 24,
                        "subparts": [
                            {"label": "Task 4.1", "description": "Implement recursive Quicksort partitioning function", "marks": 12},
                            {"label": "Task 4.2", "description": "Execute test harness with normal, extreme, and abnormal inputs", "marks": 12}
                        ]
                    }
                ],
                dataset_required=True,
                dataset_description="CANDIDATES.csv file containing candidate assessment data"
            )
        else:
            return ExamBlueprint(
                title="H2 Computing Written Examination (Paper 1 / 9569)",
                paper_type="theory",
                syllabus_code="9569",
                paper_number="01",
                total_marks=total_marks,
                learning_objectives=[
                    "Analyze logical specifications and complete decision tables",
                    "Trace recursive algorithm execution and determine Big-O time complexity",
                    "Design relational database schemas and convert to Third Normal Form (3NF)",
                    "Explain network protocols (TCP/IP, OSI), IP subnetting, and public key cryptography",
                    "Evaluate societal, ethical, and PDPA compliance implications of computing systems"
                ],
                sections=[
                    {
                        "number": 1,
                        "title": "Question 1: Decision Logic & Test Case Design",
                        "topic": "Section 2: Algorithms & Problem Solving",
                        "marks": 18,
                        "subparts": [
                            {"label": "(a)", "description": "Complete initial decision table for customer order rules", "marks": 6},
                            {"label": "(b)", "description": "Simplify decision table removing redundancies", "marks": 4},
                            {"label": "(c)", "description": "Write structured pseudocode implementing order validation", "marks": 8}
                        ]
                    },
                    {
                        "number": 2,
                        "title": "Question 2: Recursion, Trace Tables & Big-O Complexity",
                        "topic": "Section 2: Algorithms & Complexity",
                        "marks": 20,
                        "subparts": [
                            {"label": "(a)", "description": "Construct trace table showing call stack execution for Mystery(4)", "marks": 8},
                            {"label": "(b)", "description": "State base case condition and determine time complexity O(n)", "marks": 4},
                            {"label": "(c)", "description": "Rewrite algorithm iteratively using DO...UNTIL construct", "marks": 8}
                        ]
                    },
                    {
                        "number": 3,
                        "title": "Question 3: Relational Database Normalisation & SQL DDL/DML",
                        "topic": "Section 3: System Design & Implementation",
                        "marks": 22,
                        "subparts": [
                            {"label": "(a)", "description": "Identify repeating groups and convert relation to 1NF, 2NF, and 3NF", "marks": 10},
                            {"label": "(b)", "description": "Write SQL CREATE TABLE statements with PRIMARY & FOREIGN KEY constraints", "marks": 6},
                            {"label": "(c)", "description": "Formulate SQL SELECT query with INNER JOIN, GROUP BY, and HAVING", "marks": 6}
                        ]
                    },
                    {
                        "number": 4,
                        "title": "Question 4: Computer Networks, IP Subnetting & Security",
                        "topic": "Section 3: System Design & Networks",
                        "marks": 20,
                        "subparts": [
                            {"label": "(a)", "description": "Map TCP/IP protocol suite layers to OSI 7-layer architecture", "marks": 6},
                            {"label": "(b)", "description": "Calculate network address, broadcast address, and usable host range from CIDR /26", "marks": 6},
                            {"label": "(c)", "description": "Explain digital signature generation and verification process", "marks": 8}
                        ]
                    },
                    {
                        "number": 5,
                        "title": "Question 5: Computing Ethics, PDPA & Artificial Intelligence",
                        "topic": "Section 4: Ethics, Legislation & Emerging Tech",
                        "marks": 20,
                        "subparts": [
                            {"label": "(a)", "description": "Evaluate PDPA data protection obligations for candidate data handling", "marks": 6},
                            {"label": "(b)", "description": "Discuss algorithmic bias and fairness considerations in AI/ML grading models", "marks": 8},
                            {"label": "(c)", "description": "Propose cybersecurity countermeasures against SQL injection and phishing", "marks": 6}
                        ]
                    }
                ],
                dataset_required=False,
                dataset_description=None
            )

    def author_latex_paper(
        self,
        blueprint: ExamBlueprint,
        companion_dataset: Optional[Any] = None,
        institution: str = "Cambridge International Center",
        exam_year: str = "2026",
        exam_series: str = "SPECIMEN"
    ) -> str:
        """
        Generates full compilable LaTeX paper using the authentic Cambridge preamble.
        """
        template_name = "cambridge_practical_template.tex" if blueprint.paper_type == "practical" else "cambridge_theory_template.tex"
        template_path = TEMPLATES_DIR / template_name
        
        with open(template_path, "r", encoding="utf-8") as f:
            template_code = f.read()

        # Build prompt for Gemini to generate the body LaTeX
        dataset_info = ""
        if companion_dataset:
            dataset_info = f"""
Companion Dataset Information:
Filename: {companion_dataset.filename}
Columns: {', '.join(companion_dataset.columns)}
Sample data preview:
{companion_dataset.csv_content[:500]}
"""

        body_prompt = f"""
You are an expert Cambridge Computer Science paper author.
Generate the complete examination question body in rigid LaTeX syntax for the following blueprint.

Paper Type: {blueprint.paper_type.upper()}
Syllabus: {blueprint.syllabus_code} Paper {blueprint.paper_number}
Total Raw Marks: {blueprint.total_marks}

Blueprint:
{blueprint.model_dump_json(indent=2)}

{dataset_info}

CRITICAL FORMATTING & CONTEXTUAL RULES:
1. For PRACTICAL papers:
   - At the VERY TOP of the paper (before Task 1), ALWAYS include this exact general instruction:
     \\noindent Your program code and output for each of Task 1 to 4 should be saved in a single \\texttt{{.ipynb}} file. For example, your program code and output for Task 1 should be saved as:\\par\\vspace{{0.4em}}
     \\noindent\\texttt{{TASK1\\_<your name>\\_<centre number>\\_<index number>.ipynb}}\\par\\vspace{{1.0em}}
   - For each Task X:
     * Start with \\maintask{{X}} (which automatically outputs "Task X" and "Name your Jupyter Notebook as: TASKX_<your name>_<centre number>_<index number>.ipynb").
     * Provide an EXTENDED, REAL-WORLD SCENARIO narrative background for the technical challenge.
     * Before the subtasks, include \\tasksubtaskintro{{X}} EXACTLY ONCE per task (which outputs the subtask comment instructions and the left-aligned In [1]: #Task X.1 Program code / Output: box). Do NOT repeat this instruction box more than once in a task.
     * Use \\subtask{{X.1}}, \\subtask{{X.2}}, \\subtask{{X.3}}, etc. for subtask headers.
     * Structure subtask instructions with clear, concise bullet points (using \\begin{{itemize}} \\item ... \\end{{itemize}}).
     * PYTHON SIGNATURE CONVENTION: In Python questions, write plain function headers WITHOUT type annotations or return arrows (e.g. write `def search(arr, target):` NOT `def search(arr: list, target: int) -> bool:` or `--> Boolean`). Explain parameter roles and return values in natural English.
     * ALWAYS use \\Marks{{<n>}} directly at the end of each question part on the SAME line (e.g. `\\item Implement the search algorithm. \\Marks{{4}}`). Never insert a newline `\\\\` or blank line before `\\Marks{{<n>}}`.
     * At the end of Task X, include: \\taskfooter{{X}} (which prints "Save your Jupyter Notebook for Task X.").
     * Include \\newpage and \\TurnOver between major tasks.

2. For THEORY papers:
   - Begin questions with a WELL-DEVELOPED DOMAIN SCENARIO establishing background context, business rules, hardware specs, or database schema.
   - Wrap the questions in \\begin{{questions}} ... \\end{{questions}}.
   - Use \\item for main questions.
   - Use \\begin{{parts}} \\item ... \\end{{parts}} for question subparts.
   - Use \\begin{{subparts}} \\item ... \\end{{subparts}} for question sub-subparts.
   - Use \\begin{{pseudocode}} ... \\end{{pseudocode}} for pseudocode listings.
   - Use standard tabular environments for decision tables, trace tables, and comparison matrices.
   - ALWAYS place \\Marks{{<n>}} directly at the end of the question text on the SAME line (e.g. `\\item Complete the truth table. \\Marks{{3}}`). Never insert `\\\\` before `\\Marks{{<n>}}`.
   - Include \\newpage and \\TurnOver between pages where appropriate.

3. General LaTeX Rules:
   - DO NOT output \\documentclass or \\begin{{document}} or \\end{{document}} - ONLY output the inner body to replace % __AGENT_BODY_SLOT__.
   - Properly escape special characters: use \\_ for underscores, \\% for percents, \\& for ampersands, \\# for hashes.
   - Use \\code{{...}} for inline identifiers.
"""
        client = AppConfig.get_gemini_client()
        latex_body = ""
        if client and hasattr(client, "GenerativeModel"):
            try:
                model = client.GenerativeModel(AppConfig.DEFAULT_MODEL)
                response = model.generate_content(body_prompt)
                latex_body = response.text
                # Strip any accidental markdown formatting or full doc headers
                latex_body = latex_body.replace("```latex", "").replace("```", "").strip()
            except Exception as e:
                print(f"[QuestionAuthor] Gemini LaTeX authoring failed/skipped: {e}")

        if not latex_body:
            latex_body = self._generate_fallback_latex_body(blueprint, companion_dataset)
        latex_body = self._normalize_marks_spacing(latex_body)

        # Inject into golden template
        full_tex = template_code
        full_tex = full_tex.replace("((INSTITUTION))", institution)
        full_tex = full_tex.replace("((EXAM_YEAR))", exam_year)
        full_tex = full_tex.replace("((EXAM_YEAR_SHORT))", exam_year[-2:] if len(exam_year) >= 2 else "26")
        full_tex = full_tex.replace("((SYLLABUS_CODE))", blueprint.syllabus_code)
        full_tex = full_tex.replace("((PAPER_NUMBER))", blueprint.paper_number)
        full_tex = full_tex.replace("((EXAM_SERIES))", exam_series)
        full_tex = full_tex.replace("((TOTAL_MARKS))", str(blueprint.total_marks))
        full_tex = full_tex.replace("% __AGENT_BODY_SLOT__", latex_body)

        return full_tex

    def author_mark_scheme(
        self,
        blueprint: ExamBlueprint,
        latex_paper_source: str,
        institution: str = "Cambridge International Center",
        exam_year: str = "2026",
        exam_series: str = "SPECIMEN"
    ) -> str:
        """
        Generates Cambridge-compliant Mark Scheme with granular partial credits and AO allocations.
        """
        template_path = TEMPLATES_DIR / "mark_scheme_template.tex"
        with open(template_path, "r", encoding="utf-8") as f:
            template_code = f.read()

        ms_prompt = f"""
You are a Principal Cambridge Examiner for Computer Science (9618/0478).
Create the complete, publication-grade Mark Scheme corresponding to this exam paper:

Blueprint:
{blueprint.model_dump_json(indent=2)}

Format each question's rubric as a clean Cambridge Mark Scheme table using:
\\begin{{tabularx}}{{\\linewidth}}{{|p{{2.2cm}}|X|c|p{{5.0cm}}|}}
\\hline
\\textbf{{Question}} & \\textbf{{Answer / Indicative Content}} & \\textbf{{Marks}} & \\textbf{{Guidance / Partial Credit}} \\\\
\\hline
...
\\hline
\\end{{tabularx}}

Provide exact python/pseudocode solutions, exact point awards, and common candidate misconceptions.
Output ONLY the LaTeX body to replace % __AGENT_BODY_SLOT__.
"""
        client = AppConfig.get_gemini_client()
        ms_body = ""
        if client and hasattr(client, "GenerativeModel"):
            try:
                model = client.GenerativeModel(AppConfig.DEFAULT_MODEL)
                response = model.generate_content(ms_prompt)
                ms_body = response.text.replace("```latex", "").replace("```", "").strip()
            except Exception as e:
                print(f"[QuestionAuthor] Gemini Mark Scheme generation skipped/failed: {e}")

        if not ms_body:
            ms_body = self._generate_fallback_mark_scheme_body(blueprint)

        full_ms = template_code
        full_ms = full_ms.replace("((INSTITUTION))", institution)
        full_ms = full_ms.replace("((EXAM_YEAR))", exam_year)
        full_ms = full_ms.replace("((EXAM_YEAR_SHORT))", exam_year[-2:] if len(exam_year) >= 2 else "26")
        full_ms = full_ms.replace("((SYLLABUS_CODE))", blueprint.syllabus_code)
        full_ms = full_ms.replace("((PAPER_NUMBER))", blueprint.paper_number)
        full_ms = full_ms.replace("((EXAM_SERIES))", exam_series)
        full_ms = full_ms.replace("((TOTAL_MARKS))", str(blueprint.total_marks))
        full_ms = full_ms.replace("% __AGENT_BODY_SLOT__", ms_body)

        return full_ms

    def author_single_task(
        self,
        prompt: str,
        paper_type: str = "practical",
        category: str = "sec1_linear_adt",
        task_number: int = 1,
        total_marks: int = 25,
        companion_dataset: Optional[Any] = None,
        teacher_style: Optional[Dict[str, Any]] = None,
        retrieved_context: str = ""
    ) -> Dict[str, Any]:
        """
        Authors an isolated, self-contained single task (Task N / Question N).
        """
        style = teacher_style or self.preference_learner.get_style(category)
        preferred_depth = style.get("preferred_depth", "long_contextual") if style else "long_contextual"
        is_contextual = "contextual" in prompt.lower() or "long_contextual" in preferred_depth

        contextual_note = """
CONTEXTUAL DIRECTIVES:
- Provide an authentic, real-world scenario narrative establishing the business/engineering domain.
- Break down subtasks with structured, step-by-step instructions specifying exact signatures, data types, validation checks, and return values.
""" if is_contextual else ""

        if paper_type == "practical":
            structure_rules = f"""
CRITICAL STRUCTURE REQUIREMENTS (PAPER 2 PRACTICAL):
1. Start with \\maintask{{{task_number}}} (which automatically formats "Task {task_number}" and "Name your Jupyter Notebook as: TASK{task_number}_<your name>_<centre number>_<index number>.ipynb").
2. Provide the domain scenario technical challenge description.
3. Include \\tasksubtaskintro{{{task_number}}} EXACTLY ONCE before the subtasks (this formats the subtask comment instructions and the left-aligned In [1]: #Task {task_number}.1 Program code / Output: box).
4. For each subtask, use \\subtask{{{task_number}.1}}, \\subtask{{{task_number}.2}}, etc. with structured bullet points (\\begin{{itemize}} \\item ... \\end{{itemize}}). Place \\Marks{{<n>}} directly at the end of the text on the SAME line (do not insert `\\\\` or newlines before `\\Marks{{<n>}}`).
5. PYTHON SIGNATURE CONVENTION: Use plain function headers WITHOUT type annotations or return arrows (e.g. `def search(arr, target):` NOT `def search(arr: list, target: int) -> bool:` or `--> Boolean`). Explain parameter roles and return values in natural English.
6. At the end of the task, output: \\taskfooter{{{task_number}}}.
"""
        else:
            structure_rules = f"""
CRITICAL STRUCTURE REQUIREMENTS (PAPER 1 THEORY):
1. Start with \\item followed by the problem scenario, technical background, specifications, or business rules. (DO NOT output \\begin{{questions}} or \\end{{questions}} for this single question; output only this question's \\item body).
2. STRICT PROHIBITION: DO NOT USE \\maintask, \\tasksubtaskintro, \\taskfooter, Jupyter notebook names (.ipynb), #Task comments, or In [1]: boxes! These are strictly for Practical programming exams and must NOT appear in Theory papers.
3. Structure subparts using \\begin{{parts}} \\item ... \\end{{parts}} and sub-subparts using \\begin{{subparts}} \\item ... \\end{{subparts}}.
4. For pseudocode listings, use \\begin{{pseudocode}} ... \\end{{pseudocode}} (with 2-digit line numbers 01, 02, ...).
5. For decision tables, trace tables, or comparison grids, use standard LaTeX tabular environments.
6. For database schemas, underline primary keys with \\uline{{...}} and dashed-underline foreign keys with \\dashuline{{...}}.
7. ALWAYS place \\Marks{{<n>}} directly at the end of each question part on the SAME line (e.g. `\\item Complete the truth table. \\Marks{{3}}`). Never insert `\\\\` or blank lines before `\\Marks{{<n>}}`.
"""

        single_prompt = f"""
You are a Principal Examiner for Singapore-Cambridge GCE A-Level H2 Computing (9569).
Author a self-contained, high-quality examination task for:
- Paper Type: {paper_type.upper()} ({('Paper 2 Practical' if paper_type == 'practical' else 'Paper 1 Theory')})
- Task / Question Number: {task_number}
- Syllabus Topic / Category: {category}
- Total Marks for this task: {total_marks}
- User Prompt: {prompt}
{contextual_note}

{structure_rules}

OUTPUT FORMAT:
Return a JSON object matching this schema:
{{
  "task_number": {task_number},
  "title": "{'Task' if paper_type == 'practical' else 'Question'} {task_number}: <Title describing the technical challenge>",
  "topic": "{category}",
  "marks": {total_marks},
  "latex_code": "<LaTeX body for this single task>",
  "mark_scheme_code": "<LaTeX tabularx rows for this task's mark scheme table>"
}}
"""
        client = AppConfig.get_gemini_client()
        if client and hasattr(client, "GenerativeModel"):
            try:
                model = client.GenerativeModel(AppConfig.DEFAULT_MODEL)
                response = model.generate_content(
                    single_prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                if data.get("latex_code"):
                    data["latex_code"] = self._normalize_marks_spacing(data["latex_code"])
                return data
            except Exception as e:
                print(f"[QuestionAuthor] Gemini single task authoring failed: {e}")

        # Fallback single task
        if paper_type == "practical":
            fb_latex = f"""
\\maintask{{{task_number}}}

A linear data structure problem requires storing and manipulating customer records using Python.

\\tasksubtaskintro{{{task_number}}}

\\subtask{{{task_number}.1}}

Write program code to initialise the data structure and implement the insertion function with bounds checking. \\Marks{{6}}

\\subtask{{{task_number}.2}}

Write program code to search and retrieve items from the data structure, handling empty or missing items. \\Marks{{6}}

\\subtask{{{task_number}.3}}

Write driver program code to execute the system with sample test data and display summary metrics. \\Marks{{{total_marks - 12}}}

\\taskfooter{{{task_number}}}
"""
            fb_ms = f"""
\\textbf{{Task {task_number}.1}} & Implement insertion with bounds checking & \\textbf{{6}} & 1 mark per valid point (bounds check, assignment, pointer update) \\\\
\\hline
\\textbf{{Task {task_number}.2}} & Implement search and retrieval logic & \\textbf{{6}} & 1 mark for loop, 1 mark for equality check, 1 mark for empty handling \\\\
\\hline
\\textbf{{Task {task_number}.3}} & Driver execution and boundary test verification & \\textbf{{{total_marks - 12}}} & Full execution with output display \\\\
\\hline
"""
        else:
            fb_latex = f"""
\\item An algorithm performs data processing and analysis within an enterprise network.

\\begin{{parts}}
  \\item State two advantages of using a hash table compared to a linear array for fast record lookup. \\Marks{{4}}
  \\item Construct a trace table showing the step-by-step state changes for the hashing function with collision resolution. \\Marks{{8}}
  \\item Evaluate the Big-O time complexity of search operations in the worst case and average case, justifying your answer. \\Marks{{{total_marks - 12}}}
\\end{{parts}}
"""
            fb_ms = f"""
\\textbf{{Q{task_number}(a)}} & 2 distinct advantages of hash table explained & \\textbf{{4}} & 2 marks per valid advantage (O(1) average lookup, direct indexing) \\\\
\\hline
\\textbf{{Q{task_number}(b)}} & Correct trace table showing collision resolution steps & \\textbf{{8}} & 1 mark per correct row/state \\\\
\\hline
\\textbf{{Q{task_number}(c)}} & Worst case O(n) and average case O(1) Big-O justification & \\textbf{{{total_marks - 12}}} & Full justification with collision chaining explanation \\\\
\\hline
"""

        return {
            "task_number": task_number,
            "title": f"{'Task' if paper_type == 'practical' else 'Question'} {task_number}: Technical Challenge ({category})",
            "topic": category,
            "marks": total_marks,
            "latex_code": self._normalize_marks_spacing(fb_latex.strip()),
            "mark_scheme_code": fb_ms.strip(),
            "paper_type": paper_type
        }

    def refine_single_task(
        self,
        current_task: Dict[str, Any],
        refinement_prompt: str,
        paper_type: str = "practical"
    ) -> Dict[str, Any]:
        """
        Refines an existing single task using conversational prompting.
        """
        paper_format_rules = """
- For PRACTICAL papers: Keep \\maintask, \\tasksubtaskintro, \\subtask, \\taskfooter, and Jupyter notebook naming conventions.
- For THEORY papers: Keep \\item, \\begin{parts}, \\begin{subparts}, \\begin{pseudocode}, and \\Marks. Strictly DO NOT introduce \\maintask, \\tasksubtaskintro, \\taskfooter, or Jupyter notebook references!
"""
        refine_instruction = f"""
You are a Principal Cambridge Examiner.
Refine and update this specific exam task based on the educator's feedback:

PAPER TYPE: {paper_type.upper()}
{paper_format_rules}

CURRENT TASK:
Title: {current_task.get('title')}
Marks: {current_task.get('marks')}
LaTeX Code:
{current_task.get('latex_code')}

Mark Scheme Code:
{current_task.get('mark_scheme_code')}

EDUCATOR REFINEMENT INSTRUCTIONS:
{refinement_prompt}

OUTPUT FORMAT:
Return a valid JSON object matching this schema with the updated code:
{{
  "task_number": {current_task.get('task_number', 1)},
  "title": "{current_task.get('title', 'Refined Task')}",
  "topic": "{current_task.get('topic', 'Topic')}",
  "marks": {current_task.get('marks', 25)},
  "latex_code": "<Refined LaTeX code>",
  "mark_scheme_code": "<Refined LaTeX mark scheme tabular rows>"
}}
"""
        client = AppConfig.get_gemini_client()
        if client and hasattr(client, "GenerativeModel"):
            try:
                model = client.GenerativeModel(AppConfig.DEFAULT_MODEL)
                response = model.generate_content(
                    refine_instruction,
                    generation_config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                if data.get("latex_code"):
                    data["latex_code"] = self._normalize_marks_spacing(data["latex_code"])
                return data
            except Exception as e:
                print(f"[QuestionAuthor] Task refinement failed: {e}")

        # Fallback refinement: append refinement note comment
        updated = dict(current_task)
        updated["latex_code"] = current_task.get("latex_code", "") + f"\n% Refined with: {refinement_prompt}\n"
        updated["latex_code"] = self._normalize_marks_spacing(updated["latex_code"])
        return updated

    def renumber_task(
        self,
        task_dict: Dict[str, Any],
        new_number: int,
        paper_type: str = "practical"
    ) -> Dict[str, Any]:
        """
        Renumbers a task's LaTeX macros and labels to a new index (e.g. Task 3 -> Task 1).
        """
        old_num = task_dict.get("task_number", 1)
        if old_num == new_number:
            return task_dict

        updated = dict(task_dict)
        updated["task_number"] = new_number
        
        # Update title
        title = updated.get("title", f"Task {old_num}")
        title = re.sub(rf"Task\s+{old_num}\b", f"Task {new_number}", title, flags=re.IGNORECASE)
        title = re.sub(rf"Question\s+{old_num}\b", f"Question {new_number}", title, flags=re.IGNORECASE)
        updated["title"] = title

        # Renumber LaTeX Code
        latex = updated.get("latex_code", "")
        # \maintask{X} -> \maintask{new}
        latex = re.sub(rf"\\maintask\{{{old_num}\}}", f"\\\\maintask{{{new_number}}}", latex)
        # \subtask{X.y} -> \subtask{new.y}
        latex = re.sub(rf"\\subtask\{{{old_num}\.([0-9]+)\}}", rf"\\subtask{{{new_number}.\1}}", latex)
        # \tasksubtaskintro{X} -> \tasksubtaskintro{new}
        latex = re.sub(rf"\\tasksubtaskintro\{{{old_num}\}}", f"\\\\tasksubtaskintro{{{new_number}}}", latex)
        # \jupytercell{X} -> \jupytercell{new}
        latex = re.sub(rf"\\jupytercell\{{{old_num}\}}", f"\\\\jupytercell{{{new_number}}}", latex)
        # \taskfooter{X} -> \taskfooter{new}
        latex = re.sub(rf"\\taskfooter\{{{old_num}\}}", f"\\\\taskfooter{{{new_number}}}", latex)
        # TASKX_ -> TASK<new>_
        latex = re.sub(rf"TASK{old_num}\\_", f"TASK{new_number}\\_", latex)
        latex = re.sub(rf"Task\s+{old_num}\.([0-9]+)", rf"Task {new_number}.\1", latex)
        latex = re.sub(rf"Task\s+{old_num}\b", f"Task {new_number}", latex)
        updated["latex_code"] = self._normalize_marks_spacing(latex)

        # Renumber Mark Scheme Code
        ms = updated.get("mark_scheme_code", "")
        ms = re.sub(rf"Task\s+{old_num}\.([0-9]+)", rf"Task {new_number}.\1", ms)
        ms = re.sub(rf"Task\s+{old_num}\b", f"Task {new_number}", ms)
        ms = re.sub(rf"Q{old_num}\b", f"Q{new_number}", ms)
        updated["mark_scheme_code"] = ms

        return updated

    def refine_full_paper(
        self,
        latex_paper_source: str,
        mark_scheme_source: str,
        refinement_prompt: str,
        paper_type: str = "practical"
    ) -> Dict[str, str]:
        """
        Refines a full LaTeX paper and mark scheme based on educator's natural language conversational instructions.
        """
        prompt = f"""
You are an expert Cambridge Computer Science examiner and LaTeX editor.
The educator wishes to refine and edit the working examination paper and mark scheme.

EDUCATOR'S REFINEMENT REQUEST:
{refinement_prompt}

CURRENT WORKING LATEX PAPER:
{latex_paper_source}

CURRENT WORKING MARK SCHEME:
{mark_scheme_source}

INSTRUCTIONS:
1. Apply the requested changes precisely to both the question paper and matching mark scheme.
2. Maintain authentic Cambridge formatting (\\maintask, \\subtask, \\jupytercell, \\Marks, etc. for practical; \\begin{{questions}}, \\item, \\begin{{parts}}, \\Marks for theory).
3. Return a valid JSON object matching this schema:
{{
  "latex_source": "<complete updated LaTeX exam paper source>",
  "mark_scheme_source": "<complete updated LaTeX mark scheme source>"
}}
"""
        client = AppConfig.get_gemini_client()
        if client and hasattr(client, "GenerativeModel"):
            try:
                model = client.GenerativeModel(AppConfig.DEFAULT_MODEL)
                response = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                if data.get("latex_source") and data.get("mark_scheme_source"):
                    data["latex_source"] = self._normalize_marks_spacing(data["latex_source"])
                    return data
            except Exception as e:
                print(f"[QuestionAuthor] refine_full_paper error: {e}")

        # Fallback
        return {
            "latex_source": latex_paper_source,
            "mark_scheme_source": mark_scheme_source
        }

    def assemble_full_paper(
        self,
        tasks_list: List[Dict[str, Any]],
        paper_type: str = "practical",
        syllabus_code: str = "9569",
        paper_number: str = "02",
        institution: str = "HelloWorld Junior College",
        exam_year: str = "2027",
        exam_series: str = "PRELIM"
    ) -> Dict[str, str]:
        """
        Assembles a list of individual task dictionaries into full compilable LaTeX paper and mark scheme.
        """
        template_name = "cambridge_practical_template.tex" if paper_type == "practical" else "cambridge_theory_template.tex"
        template_path = TEMPLATES_DIR / template_name
        with open(template_path, "r", encoding="utf-8") as f:
            paper_template = f.read()

        ms_template_path = TEMPLATES_DIR / "mark_scheme_template.tex"
        with open(ms_template_path, "r", encoding="utf-8") as f:
            ms_template = f.read()

        # Combine LaTeX bodies with page breaks
        body_parts = []
        for idx, t in enumerate(tasks_list):
            raw_code = t.get("latex_code", "").strip()
            if not raw_code:
                continue
            
            if paper_type == "theory":
                # Clean any stray \begin{questions} or \end{questions} from single-question bodies
                clean_code = re.sub(r"\\begin\{questions\}", "", raw_code)
                clean_code = re.sub(r"\\end\{questions\}", "", clean_code).strip()
                if clean_code and not clean_code.startswith(r"\item") and not clean_code.startswith(r"\question"):
                    clean_code = f"\\item {clean_code}"
                body_parts.append(self._normalize_marks_spacing(clean_code))
            else:
                body_parts.append(self._normalize_marks_spacing(raw_code))

        separator = "\n\n\\newpage\n\\TurnOver\n\n"
        if paper_type == "theory":
            combined_body = "\\begin{questions}\n\n" + separator.join(body_parts) + "\n\n\\end{questions}"
        else:
            practical_body = separator.join(body_parts)
            # Ensure top general .ipynb instruction is present at the very beginning of the practical paper
            general_ipynb_instruction = (
                r"\noindent Your program code and output for each of Task 1 to 4 should be saved in a single \texttt{.ipynb} file. "
                r"For example, your program code and output for Task 1 should be saved as:\par\vspace{0.4em}" "\n"
                r"\noindent\texttt{TASK1\_<your name>\_<centre number>\_<index number>.ipynb}\par\vspace{1.0em}" "\n\n"
            )
            if "Your program code and output for each of Task" not in practical_body:
                combined_body = general_ipynb_instruction + practical_body
            else:
                combined_body = practical_body
        combined_body = self._normalize_marks_spacing(combined_body)

        # Build Full LaTeX Paper
        full_paper = paper_template
        full_paper = full_paper.replace("((INSTITUTION))", institution)
        full_paper = full_paper.replace("((EXAM_YEAR))", exam_year)
        full_paper = full_paper.replace("((EXAM_YEAR_SHORT))", exam_year[-2:] if len(exam_year) >= 2 else "26")
        full_paper = full_paper.replace("((SYLLABUS_CODE))", syllabus_code)
        full_paper = full_paper.replace("((PAPER_NUMBER))", paper_number)
        full_paper = full_paper.replace("((EXAM_SERIES))", exam_series)
        full_paper = full_paper.replace("% __AGENT_BODY_SLOT__", combined_body)

        # Build Full Mark Scheme
        ms_rows = []
        for t in tasks_list:
            ms_rows.append(t.get("mark_scheme_code", "").strip())
        
        combined_ms_table = f"""
\\begin{{tabularx}}{{\\linewidth}}{{|p{{2.5cm}}|X|c|p{{4.5cm}}|}}
\\hline
\\textbf{{Question}} & \\textbf{{Answer / Indicative Content}} & \\textbf{{Marks}} & \\textbf{{Guidance / Partial Credit}} \\\\
\\hline
{chr(10).join(ms_rows)}
\\hline
\\end{{tabularx}}
"""
        total_marks = sum(t.get("marks", 25) for t in tasks_list)
        full_ms = ms_template
        full_ms = full_ms.replace("((INSTITUTION))", institution)
        full_ms = full_ms.replace("((EXAM_YEAR))", exam_year)
        full_ms = full_ms.replace("((EXAM_YEAR_SHORT))", exam_year[-2:] if len(exam_year) >= 2 else "26")
        full_ms = full_ms.replace("((SYLLABUS_CODE))", syllabus_code)
        full_ms = full_ms.replace("((PAPER_NUMBER))", paper_number)
        full_ms = full_ms.replace("((EXAM_SERIES))", exam_series)
        full_ms = full_ms.replace("((TOTAL_MARKS))", str(total_marks))
        full_ms = full_ms.replace("% __AGENT_BODY_SLOT__", combined_ms_table)

        return {
            "latex_source": full_paper,
            "mark_scheme_source": full_ms,
            "total_marks": total_marks
        }

    def _generate_fallback_latex_body(self, blueprint: ExamBlueprint, companion_dataset: Optional[Any]) -> str:
        """Fallback LaTeX body generator."""
        if blueprint.paper_type == "practical":
            return r"""
\noindent Your program code and output for each of Task 1 to 4 should be saved in a single \texttt{.ipynb} file. For example, your program code and output for Task 1 should be saved as:\par\vspace{0.4em}
\noindent\texttt{TASK1\_<your name>\_<centre number>\_<index number>.ipynb}\par\vspace{1.0em}

\maintask{1}

A denary number can be converted to binary using the division by 2 method and a stack abstract data type.
The stack can store integer data items in a 1-dimensional list. A top of stack pointer stores the index of the next available space.

\tasksubtaskintro{1}

\subtask{1.1}

The function \code{push()} takes the stack, the top of stack pointer, and the data item to push as parameters. The function stores the data item and returns the updated top of stack pointer.

Write program code for the function \code{push()}. \Marks{4}

\subtask{1.2}

The function \code{pop()} takes the stack and top of stack pointer as parameters. It returns the popped item and the updated top of stack pointer. If empty, it returns \code{False}.

Write program code for the function \code{pop()}. \Marks{4}

\subtask{1.3}

The function \code{main()} initialises the stack and prompts the user for a positive integer. It pushes remainders to the stack and pops them to output the binary representation.

Write program code for \code{main()} and test with inputs 0, 22, and 46967. \Marks{12}

\taskfooter{1}

\newpage
\TurnOver

\maintask{2}

The file \code{CANDIDATES.csv} contains candidate assessment records in CSV format with fields: \code{CandidateID}, \code{CandidateName}, \code{Gender}, \code{AssessmentScore}, \code{CourseworkScore}, \code{FinalStatus}.

\tasksubtaskintro{2}

\subtask{2.1}

Write program code to open \code{CANDIDATES.csv} and load records into a 2-dimensional list or list of objects. \Marks{6}

\subtask{2.2}

Write program code to calculate and display the cohort average score and the highest scoring candidate. \Marks{8}

\subtask{2.3}

Write program code to output all candidates achieving 'Distinction' to a new file named \code{DISTINCTIONS.txt}. \Marks{6}

\taskfooter{2}
"""
        else:
            return r"""
\begin{questions}

\item A company operates a stock inventory control system.
\begin{tightitemize}
  \item Customers place orders specifying quantity and item ID.
  \item Orders are accepted if stock is available and customer account credit is sufficient.
  \item If stock is unavailable but credit is sufficient, the order is placed on back-order.
\end{tightitemize}

\begin{parts}
  \item Copy and complete the decision table for the ordering logic.
  
  \vspace{0.4em}
  \begin{tabular}{|l|l|c|c|c|c|}
    \hline
    \multicolumn{2}{|c|}{} & \multicolumn{4}{c|}{\textbf{Rules}} \\
    \hline
    \multirow{2}{*}{\textbf{Conditions}} 
    & stock available & Y & Y & N & N \\ \cline{2-6}
    & sufficient credit & Y & N & Y & N \\ \hline
    \multirow{3}{*}{\textbf{Actions}}
    & accept order & X & & & \\ \cline{2-6}
    & back-order & & & X & \\ \cline{2-6}
    & reject order & & X & & X \\ \hline
  \end{tabular}
  \Marks{4}

  \item Write Cambridge structured pseudocode to input order quantity and determine the order status. \Marks{6}
  
  \item Explain the difference between normal, extreme, and abnormal test data. \Marks{4}
\end{parts}

\newpage
\TurnOver

\item A recursive algorithm is defined as follows:

\begin{pseudocode}
FUNCTION Mystery(n : INTEGER) RETURNS INTEGER
  IF n <= 1 THEN
    RETURN 1
  ELSE
    RETURN n * Mystery(n - 1)
  ENDIF
ENDFUNCTION
\end{pseudocode}

\begin{parts}
  \item State the base case condition for the function \code{Mystery}. \Marks{1}
  \item Construct a trace table showing the stack frames for the call \code{Mystery(4)}. \Marks{6}
  \item Rewrite the function \code{Mystery} using an iterative loop construct. \Marks{8}
\end{parts}

\end{questions}
"""

    def _generate_fallback_mark_scheme_body(self, blueprint: ExamBlueprint) -> str:
        """Fallback Mark Scheme body."""
        return r"""
\begin{tabularx}{\linewidth}{|p{2.2cm}|X|c|p{4.8cm}|}
\hline
\textbf{Question} & \textbf{Answer / Indicative Content} & \textbf{Marks} & \textbf{Guidance} \\
\hline
\textbf{Task 1.1 / Q1(a)} &
1 mark per valid point:
\begin{itemize}[leftmargin=0.4cm, itemsep=0.1em]
  \item Check for stack full condition / list expansion
  \item Assign data item to stack at top of stack pointer index
  \item Increment top of stack pointer
  \item Return updated pointer
\end{itemize}
& \textbf{4} & Allow 1 mark for correct parameter definition. \\
\hline
\textbf{Task 1.2 / Q1(b)} &
1 mark per valid point:
\begin{itemize}[leftmargin=0.4cm, itemsep=0.1em]
  \item Check for empty stack condition (pointer == 0)
  \item Decrement top of stack pointer
  \item Retrieve data item at decremented index
  \item Return item and pointer
\end{itemize}
& \textbf{4} & Do not award if data is permanently removed without pointer tracking. \\
\hline
\textbf{Task 1.3 / Q1(c)} &
1 mark for each:
\begin{itemize}[leftmargin=0.4cm, itemsep=0.1em]
  \item Initialising stack list and pointer
  \item Correct loop while number > 0
  \item Repeated modulo 2 and division by 2
  \item Correct call to push() and pop()
  \item Outputting binary representation
\end{itemize}
& \textbf{12} & Test run: 0 -> 0, 22 -> 10110, 46967 -> 1011011101110111. \\
\hline
\end{tabularx}
"""
