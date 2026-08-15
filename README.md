# EduScribe AI (ComputingScribe) 🎓

> **The adaptive co-authoring agent for technical educators:** turning syllabus standards into compiled LaTeX papers, balanced synthetic datasets, and verified mark schemes.

---

## 🌟 Overview & Real-World Pain Points Solved

Authoring rigorous technical examinations for subjects such as **Cambridge IGCSE & AS/A-Level Computer Science (9618 / 0478)** requires hours of manual typesetting, companion dataset fabrication, and rubric alignment. **EduScribe AI** is an autonomous, persistent co-authoring partner powered by **Google Cloud (Vertex AI / Gemini 3.7 Flash, Firestore, Cloud Storage, Cloud Run)** and **Streamlit**.

- 🎯 **Dual Paper Support**: Direct generation of both **Practical Papers** (Task 1 to 4 Jupyter Notebooks, Python skeleton code, CSV datasets) and **Theory Papers** (Decision tables, Trace tables, Pseudocode listings, Normalisation).
- ⚖️ **Automated Demographic Guardrails**: Guarantees 50/50 gender parity and authentic multiracial regional naming pools (Chinese, Malay, Indian, Eurasian, Caucasian) across synthetic CSV and SQL test datasets.
- 🔄 **Self-Healing Compilation Loop**: Runs headless `pdflatex` compilation; intercepts compiler errors, uses **Gemini 3.7 Flash** to diagnose and repair syntax/macros, and automatically retries.
- 🧠 **Adaptive Educator Style Learning**: Tracks evolving educator habits, question depth preferences (`short_direct` vs `long_contextual`), and mark distributions in **Google Cloud Firestore**.
- 📦 **Session Lifecycle & One-Click Bundles**: Save, restore, and export `.zip` archives containing the compiled `.pdf`, `.tex` source, companion `.csv` / `.sql`, and starter `.py` files.

---

## 🏗️ Architecture & Agentic Workflow

```
[ User Goal / Prompt ]
         │
         ▼
[ Step 1: Memory & Style Retrieval ]  (Fetches learned category profile & syllabus rules from Firestore)
         │
         ▼
[ Step 2: Blueprint Proposer ]        (Plans learning objectives & mark distribution with Gemini 3.7 Flash)
         │
         ▼
[ Step 3: Tool Execution ]            (Synthesises demographic CSV/SQL datasets & LaTeX source)
         │
         ▼
[ Step 4: Self-Healing Sandbox ] ◄──┐ (pdflatex compilation in container)
         │                          │
         ├── Error detected? ───────┘ (Captures stderr, repairs syntax with Gemini 3.7 Flash)
         │
         ▼ (Success)
[ Step 5: Multi-Artefact Bundle ]     (PDF, Mark Scheme, CSVs ready for one-click export)
```

---

## 📂 Repository Structure

```
eduscribe-ai/
├── README.md
├── requirements.txt
├── Dockerfile
├── config/
│   ├── gcp_config.py
│   └── default_preferences.json
├── templates/
│   ├── cambridge_practical_template.tex
│   ├── cambridge_theory_template.tex
│   ├── cambridge_exam_template.tex
│   └── mark_scheme_template.tex
├── src/
│   ├── agent/
│   │   ├── orchestrator.py
│   │   ├── preference_learner.py
│   │   └── session_manager.py
│   ├── ingestion/
│   │   ├── document_parser.py
│   │   └── rag_retriever.py
│   ├── generators/
│   │   ├── dataset_generator.py
│   │   └── question_author.py
│   └── sandbox/
│       ├── code_executor.py
│       └── latex_compiler.py
├── frontend/
│   ├── app.py
│   └── style.css
└── tests/
    └── test_pipeline.py
```

---

## 🚀 Quick Start Guide

### 1. Installation

```bash
# Clone repository
git clone https://github.com/your-org/EduScribe-AI.git
cd EduScribe-AI

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install latest dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration (Optional)

Create a `.env` file in the root directory:

```env
# Direct Gemini API Key
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.7-flash

# Google Cloud Platform (Optional for Vertex AI & Firestore)
GCP_PROJECT=your-gcp-project-id
GCP_LOCATION=us-central1
GCS_BUCKET_NAME=eduscribe-exam-assets
```

*(Note: If no GCP project is provided, EduScribe AI seamlessly runs in local persistent mode with full local caching and fallback previews).*

### 3. Running the Streamlit App

```bash
streamlit run frontend/app.py
```

---

## 🐳 Docker & Cloud Run Deployment

Build and run the containerized application with complete TeXLive support:

```bash
# Build Docker image
docker build -t eduscribe-ai .

# Run container locally on port 8501
docker run -p 8501:8501 -e GEMINI_API_KEY="your_api_key" eduscribe-ai

# Deploy to Google Cloud Run
gcloud run deploy eduscribe-ai \
    --source . \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated
```

---

## 🧪 Running Automated Tests

```bash
python -m unittest discover tests
```
>>>>>>> 94885b5 (feat: complete EduScribe AI with 2027 H2 Computing, Cambridge LaTeX, and Gemini 3.7 Flash)
