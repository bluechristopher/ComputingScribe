# 🎓 EduScribe AI — Hackathon Submission

**Hackathon Category:** Collaborative Partner  
*Build an agent that leads the way and takes notes. It should ask clarifying questions, guide the user step-by-step, and have a clear way to capture feedback, so it constantly adapts to the user's unique way of thinking.*

---

## 🏆 1. Compliance Checklist with Hackathon Requirements

| Requirement | EduScribe AI Implementation | Status |
| :--- | :--- | :---: |
| **Model** (Gemini 3.5 or newer) | **Gemini 3.7 Flash** used for blueprint co-authoring, LaTeX self-healing syntax repair, and adaptive feedback extraction. | ✅ **Pass** |
| **Google Agent Framework** | **Google GenAI SDK (`google-genai`)** integrated with multi-turn reasoning loops, tool calling, and RAG document indexing. | ✅ **Pass** |
| **Google Cloud Infrastructure** | **Google Cloud Run** (serverless hosting), **Google Cloud Firestore** (teacher profile persistence), **Google Artifact Registry** (container storage), **Google Cloud Build** (automated CI/CD). | ✅ **Pass** |
| **Hosted Project URL** | Publicly accessible **Google Cloud Run URL** (`.a.run.app`). | ✅ **Pass** |
| **Public Code Repository** | [https://github.com/bluechristopher/ComputingScribe](https://github.com/bluechristopher/ComputingScribe) | ✅ **Pass** |
| **Reproducible Spin-Up Guide** | Step-by-step Docker and local setup in `README.md` and automated GitHub Actions CI/CD. | ✅ **Pass** |
| **Architecture Diagram** | Comprehensive Google Cloud end-to-end dataflow diagram. | ✅ **Pass** |

---

## 📖 2. Text Description & Teacher's Perspective

### The Problem: The High-Friction Reality of Setting Technical Exams
As a Computing educator setting national and institutional examinations (such as Singapore-Cambridge GCE A-Level H2 Computing / 9569 and Cambridge AS/A-Level 9618), the authoring process is an exhausting, multi-hour ordeal:

1. **Contextual Problem Drafting Burden**: Authoring authentic, high-quality contextual scenarios (e.g. transport AFC systems, triage queues, normalized database schemas) that strictly align with syllabus learning objectives and command words takes days of drafting and refinement.
2. **Typesetting Friction (Word vs LaTeX)**: 
   - Using Microsoft Word leads to notorious alignment disasters, shifted code boxes, broken table borders, and mismatched margin brackets (`[4]`).
   - LaTeX produces flawless, publication-grade examination papers, but writing raw LaTeX requires steep expertise and significant debugging time. Colleagues without TeX expertise cannot easily contribute or maintain exam papers.
3. **Synthetic Dataset Fabrication Burden**: Practical programming papers require balanced, clean companion datasets (CSV records, SQL schemas). Manually creating these often introduces subtle data bugs or demographic biases.

### The Solution: EduScribe AI as Your Autonomous Collaborative Partner
EduScribe AI is not a generic text generator; it is a **collaborative pedagogical partner** that:
- **Leads the authoring process step-by-step**: Proposes structured exam blueprints, balances mark allotments, generates companion demographic datasets, and formats compilable LaTeX code with official Cambridge preambles.
- **Constantly adapts to the teacher's unique pedagogical style**: Tracks preferences across specific syllabus modules (e.g., preference for concise prompts vs extended contextual scenarios, code box formats, and rubric granularity) and persists them in **Google Cloud Firestore**.
- **Self-heals compilation errors**: Runs headless `pdflatex` compilation in a sandbox; if a broken macro occurs, **Gemini 3.7 Flash** diagnoses the error log and repairs the code automatically without requiring the teacher to debug TeX errors.
- **Renders on-screen typeset papers with zero LaTeX expertise required**: Educators without TeX installed can instantly view authentic Cambridge A4 exam sheets (with KaTeX math, Jupyter cells, pseudocode line numbers, and mark brackets) and export production-ready `.pdf` and `.tex` packages with a single click.

---

## 🛠️ 3. Features & Functionality

### 1. Multi-Step Collaborative Blueprint Authoring
- **Interactive Step-by-Step Guidance**: Deconstructs syllabus goals into clear tasks, learning objectives, and point distributions before authoring code.
- **Contextual Trigger Engine**: Including the keyword `'contextual'` triggers extended real-world scenario preambles and step-by-step bulleted subtask specifications for Practical papers, and well-developed domain narratives for Theory papers.

### 2. Full Dual Paper Support (H2 Computing 2027 / 9569 Standards)
- **Paper 2 (Lab-Based Practical)**: Generates Task 1 to 4 Python programming challenges, Jupyter input cells (`\jupytercell`), demographically balanced datasets (`CANDIDATES.csv`), SQL schema scripts (`SCHEMA.sql`), and starter files (`starter_task.py`).
- **Paper 1 (Written Theory)**: Generates structured questions, Cambridge pseudocode listings with two-digit line numbering (`01`, `02`, ...), decision tables with boundary conditions, trace tables, SQL queries, and networking calculations.

### 3. Demographic Fairness & Synthetic Data Synthesizer
- Enforces strict demographic guardrails across synthetic CSV and SQL companion datasets:
  - **50/50 Gender Parity** across candidate records.
  - **Multiracial Regional Naming Distributions** (Chinese, Malay, Indian, Eurasian, Caucasian naming pools) ensuring representative test data without stereotyping.

### 4. Self-Healing LaTeX Sandbox & Live Typeset Paper Sheet
- **Automated pdflatex Self-Healing**: Captures compilation stderr logs and uses Gemini 3.7 Flash to diagnose syntax locks, unescaped characters, or missing macros in an automatic 3-pass repair loop.
- **On-Screen Publication-Grade Sheet**: Renders authentic A4 exam sheets in-browser with KaTeX, running headers (`Anderson Serangoon Junior College`), page numbers, and right-aligned mark brackets (`[4]`, `[12]`).

### 5. Continuous Preference & Phrasing Learning Engine
- **Dedicated Feedback Loop (Tab 6)**: Teachers can input natural-language feedback after reviewing a draft (e.g. *"Make subtask instructions more granular with explicit return types"*).
- Gemini extracts structured pedagogical rules and updates the educator's persistent profile in **Google Cloud Firestore**.
- Grounded retrieval (RAG) indexes past school prelim papers (`.pdf`, `.docx`, `.tex`) to mimic institutional phrasing conventions.

### 6. One-Click Multi-Artifact Export Archive
- Automatically packages a complete, distribution-ready `.zip` archive containing:
  - `paper.pdf` & `paper.tex` (Exam Question Paper)
  - `mark_scheme.pdf` & `mark_scheme.tex` (Official Cambridge Mark Scheme)
  - `CANDIDATES.csv` & `SCHEMA.sql` (Companion Test Datasets)
  - `starter_task.py` (Candidate Skeleton Code)
  - `blueprint.json` (Structured Metadata)

---

## 💻 4. Technologies Used

### Google Cloud & AI Stack:
- **Gemini 3.7 Flash** (`gemini-3.7-flash`): Primary reasoning engine for blueprint formulation, contextual scenario synthesis, LaTeX self-healing code repair, and feedback extraction.
- **Google GenAI SDK (`google-genai`)**: Next-generation SDK for structured JSON output and multi-modal grounding.
- **Google Cloud Run**: Serverless container hosting in Singapore (`asia-southeast1`) with automatic HTTPS and dynamic scaling.
- **Google Cloud Firestore**: NoSQL cloud database storing teacher preference profiles, category style rules, and historical draft sessions.
- **Google Cloud Build & Artifact Registry**: Automated container packaging and continuous deployment pipeline.

### Application & Rendering Stack:
- **Streamlit**: Interactive web interface with custom high-contrast CSS styling.
- **TeXLive / pdflatex**: Headless LaTeX compilation engine inside the production container.
- **KaTeX & HTML5 Typesetting Engine**: In-browser pixel-perfect A4 exam paper sheet rendering.
- **FPDF2**: Standalone fallback PDF document generator.
- **PyPDF & Python-Docx**: Document ingestion parsers for RAG style grounding.
- **Pydantic**: Type-safe schema validation for blueprints, datasets, and sessions.

---

## 📊 5. Other Data Sources & Curricula Used

1. **Singapore-Cambridge GCE A-Level H2 Computing (Syllabus 9569 / 2027)**:
   - Section 1: Data and Data Structures (Linear & Non-Linear ADTs, BST, Hash Tables).
   - Section 2: Algorithms and Problem Solving (Quicksort, Merge sort, Decision tables, Big-O Complexity).
   - Section 3: System Design & Implementation (Python 3, OOP Polymorphism, 1NF-3NF Relational DBs, Flask, Networks & Subnetting).
   - Section 4: Ethics, Legislation & Emerging Tech (PDPA, AI Ethics, Cybersecurity).
2. **Cambridge International AS & A Level Computer Science (9618)**:
   - Standard command words, tabular mark scheme rubrics, and pseudocode specifications.
3. **Anderson Serangoon Junior College (ASJC) & Singapore Schools Past Examinations**:
   - Exemplar practical exam templates and theory decision table formatting conventions.
4. **Singapore Department of Statistics (SingStat)**:
   - Demographic cohort distributions for balanced synthetic dataset generation.

---

## 🏗️ 6. System Architecture Diagram

```mermaid
flowchart TD
    subgraph Client["Web Browser / Client Interface"]
        UI["Streamlit Frontend (app.py)"]
        Renderer["LaTeX Visual Typesetting Sheet (KaTeX / HTML5)"]
    end

    subgraph GCP["Google Cloud Platform (Singapore - asia-southeast1)"]
        CR["Google Cloud Run (eduscribe-ai Container)"]
        Firestore[("Cloud Firestore: Teacher Profiles & Learned Styles")]
        ArtifactReg["Artifact Registry: eduscribe-repo"]
        CloudBuild["Cloud Build: CI/CD Pipeline"]
    end

    subgraph AI["Google AI Services"]
        Gemini["Gemini 3.7 Flash Engine (google-genai SDK)"]
        RAG["RAG Ingestion Engine (Past Paper Grounding)"]
    end

    subgraph Sandbox["Local / Containerized Execution Sandbox"]
        TeXLive["Headless pdflatex Compiler"]
        SelfHealing["Gemini 3-Pass Diagnostic Self-Healing Loop"]
        PythonExec["Python Subprocess Runner (Starter Code Validation)"]
    end

    UI -->|1. Exam Prompt & Category| CR
    CR -->|2. Fetch Learned Teacher Style| Firestore
    CR -->|3. Query RAG Context| RAG
    CR -->|4. Propose Blueprint & Synthesize Code| Gemini
    CR -->|5. Headless pdflatex Compilation| TeXLive
    TeXLive -- Error Logs -->|6. Intercept Stderr & Repair| SelfHealing
    SelfHealing -->|7. Repaired LaTeX Code| Gemini
    CR -->|8. Save Updated Preferences| Firestore
    CR -->|9. Render Typeset Sheet & Deliver PDF/ZIP| Renderer
    Renderer --> UI

    GitHub["GitHub Repository: bluechristopher/ComputingScribe"] -->|git push main| CloudBuild
    CloudBuild --> ArtifactReg
    ArtifactReg --> CR
```

---

## 🚀 7. Spin-Up & Reproducibility Instructions

### Option A: Run via Docker (Recommended — Full TeXLive Included)

```bash
# 1. Clone repository
git clone https://github.com/bluechristopher/ComputingScribe.git
cd ComputingScribe

# 2. Build Docker container
docker build -t eduscribe-ai .

# 3. Run container with your Gemini API Key
docker run -p 8501:8501 -e GEMINI_API_KEY="YOUR_GEMINI_API_KEY" eduscribe-ai

# 4. Open in browser
http://localhost:8501
```

### Option B: Local Python Development

```powershell
# 1. Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variable
$env:GEMINI_API_KEY="YOUR_GEMINI_API_KEY"

# 4. Run automated test suite
python -m unittest tests/test_pipeline.py

# 5. Launch Streamlit application
streamlit run frontend/app.py
```
