"""
EduScribe AI - Question Author Module
Specialised authoring engine for Cambridge Practical & Theory exam papers and matching Mark Schemes.
"""

import json
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
        """
        teacher_style = teacher_style or {}
        is_contextual = "contextual" in prompt.lower() or teacher_style.get("preferred_depth") == "long_contextual"
        preferred_depth = "long_contextual" if is_contextual else teacher_style.get("preferred_depth", "long_contextual")
        target_marks = teacher_style.get("total_marks", 100)
        task_count = teacher_style.get("task_count", 4 if paper_type == "practical" else 5)

        contextual_instructions = """
CONTEXTUAL DEPTH DIRECTIVES (ACTIVE):
- For PRACTICAL (Paper 2):
  * Create an EXTENDED, REAL-WORLD SCENARIO (e.g. Singapore MRT Automated Fare Collection, Hospital Emergency Triage Queue, E-Commerce Warehouse Logistics, or Bank Transaction Ledger).
  * Structure every subtask with CLEAR, STEP-BY-STEP BULLETED POINT INSTRUCTIONS.
  * Explicitly specify data types, method signatures, return values, exception handling, and expected console/Jupyter outputs.
  * Include realistic sample records and structured test tables.

- For THEORY (Paper 1):
  * Develop a RICH, MULTI-PARAGRAPH DOMAIN SCENARIO establishing entities, business rules, hardware/network architecture, and security constraints.
  * All question parts must tie directly into the scenario (e.g. applying 1NF-3NF normalisation to the scenario's functional dependencies, constructing trace tables for scenario algorithms, calculating subnets for the scenario branch offices, or evaluating PDPA/AI ethics for scenario data handling).
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
Target Total Marks: {target_marks}
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
                        "marks": 25,
                        "subparts": [
                            {"label": "Task 3.1", "description": "Define superclass AssessmentItem with constructor and getters", "marks": 8},
                            {"label": "Task 3.2", "description": "Define subclass PracticalAssessment overriding calculateScore()", "marks": 9},
                            {"label": "Task 3.3", "description": "Instantiate polymorphically and verify method dispatch", "marks": 8}
                        ]
                    },
                    {
                        "number": 4,
                        "title": "Task 4: Sorting, Searching & Algorithm Efficiency",
                        "topic": "Section 2: Algorithms & Complexity (Quicksort / Binary Search)",
                        "marks": 25,
                        "subparts": [
                            {"label": "Task 4.1", "description": "Implement recursive Quicksort partitioning function", "marks": 13},
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
   - Provide an EXTENDED, REAL-WORLD SCENARIO preamble for each task (e.g. smart ticketing, banking, hospital patient records).
   - Use \\maintask{{1}}, \\maintask{{2}}, etc. for main tasks.
   - Use \\subtask{{1.1}}, \\subtask{{1.2}}, etc. for subtasks.
   - Break down subtask instructions into CLEAR, STRUCTURED BULLETED POINTS (using \\begin{{itemize}} \\item ... \\end{{itemize}} or itemized steps).
   - Use \\jupytercell{{<in_num>}}{{\\#Task X.Y\\\\Program code}} for code starter boxes.
   - Use \\begin{{testcases}} \\item Test 1: ... \\end{{testcases}} for test cases.
   - ALWAYS use \\Marks{{<n>}} at the end of each question part for right-aligned bracketed marks.
   - Include \\newpage and \\TurnOver between major tasks.

2. For THEORY papers:
   - Begin questions with a WELL-DEVELOPED DOMAIN SCENARIO establishing background context, business rules, hardware specs, or database schema.
   - Wrap the questions in \\begin{{questions}} ... \\end{{questions}}.
   - Use \\item for main questions.
   - Use \\begin{{parts}} \\item ... \\end{{parts}} for question subparts.
   - Use \\begin{{subparts}} \\item ... \\end{{subparts}} for sub-subparts.
   - Use \\begin{{pseudocode}} ... \\end{{pseudocode}} for pseudocode listings.
   - Use standard tabular environments for decision tables, trace tables, and comparison matrices.
   - ALWAYS use \\Marks{{<n>}} at the end of each question part.
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

        # Inject into golden template
        full_tex = template_code
        full_tex = full_tex.replace("((INSTITUTION))", institution)
        full_tex = full_tex.replace("((EXAM_YEAR))", exam_year)
        full_tex = full_tex.replace("((EXAM_YEAR_SHORT))", exam_year[-2:] if len(exam_year) >= 2 else "26")
        full_tex = full_tex.replace("((SYLLABUS_CODE))", blueprint.syllabus_code)
        full_tex = full_tex.replace("((PAPER_NUMBER))", blueprint.paper_number)
        full_tex = full_tex.replace("((EXAM_SERIES))", exam_series)
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

    def _generate_fallback_latex_body(self, blueprint: ExamBlueprint, companion_dataset: Optional[Any]) -> str:
        """Fallback LaTeX body generator."""
        if blueprint.paper_type == "practical":
            return r"""
\textbf{Instruction to candidates:}

Your program code and output for each of Task 1 to 4 should be saved in a single \code{.ipynb} file. For example, your program code and output for Task 1 should be saved as:

\code{TASK1\_<your name>\_<centre number>\_<index number>.ipynb}

\maintask{1}

Name your Jupyter Notebook as: \code{TASK1\_<your name>\_<centre number>\_<index number>.ipynb}

A denary number can be converted to binary using the division by 2 method and a stack abstract data type.
The stack can store integer data items in a 1-dimensional list. A top of stack pointer stores the index of the next available space.

\jupytercell{1}{\# Task 1.1\\Program code}

\subtask{1.1}

The function \code{push()} takes the stack, the top of stack pointer, and the data item to push as parameters. The function stores the data item and returns the updated top of stack pointer.

Write program code for the function \code{push()}. \Marks{4}

\subtask{1.2}

The function \code{pop()} takes the stack and top of stack pointer as parameters. It returns the popped item and the updated top of stack pointer. If empty, it returns \code{False}.

Write program code for the function \code{pop()}. \Marks{4}

\subtask{1.3}

The function \code{main()} initialises the stack and prompts the user for a positive integer. It pushes remainders to the stack and pops them to output the binary representation.

Write program code for \code{main()} and test with inputs 0, 22, and 46967. \Marks{12}

\newpage
\TurnOver

\maintask{2}

Name your Jupyter Notebook as: \code{TASK2\_<your name>\_<centre number>\_<index number>.ipynb}

The file \code{CANDIDATES.csv} contains candidate assessment records in CSV format with fields: \code{CandidateID}, \code{CandidateName}, \code{Gender}, \code{AssessmentScore}, \code{CourseworkScore}, \code{FinalStatus}.

\subtask{2.1}

Write program code to open \code{CANDIDATES.csv} and load records into a 2-dimensional list or list of objects. \Marks{6}

\subtask{2.2}

Write program code to calculate and display the cohort average score and the highest scoring candidate. \Marks{8}

\subtask{2.3}

Write program code to output all candidates achieving 'Distinction' to a new file named \code{DISTINCTIONS.txt}. \Marks{6}
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
