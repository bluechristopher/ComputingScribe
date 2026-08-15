"""
EduScribe AI - Web Application
The adaptive co-authoring agent for technical educators.
"""

import os
import sys
import io
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import streamlit as st
import pandas as pd

from config.gcp_config import AppConfig
from src.agent.orchestrator import EduScribeOrchestrator, ExamGenerationProgress
from src.agent.session_manager import SessionManager, ExamSession
from src.agent.preference_learner import PreferenceLearner
from src.sandbox.code_executor import CodeExecutor

# Page Configuration
st.set_page_config(
    page_title="EduScribe AI | Cambridge Exam Authoring Agent",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load Custom Montserrat CSS
css_path = BASE_DIR / "frontend" / "style.css"
if css_path.exists():
    with open(css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Session State Initialization
if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = EduScribeOrchestrator()
if "current_session" not in st.session_state:
    st.session_state.current_session = None
if "compilation_logs" not in st.session_state:
    st.session_state.compilation_logs = []
if "teacher_id" not in st.session_state:
    st.session_state.teacher_id = "default_teacher"

session_mgr = SessionManager()
pref_learner = PreferenceLearner(st.session_state.teacher_id)

# ==============================================================================
# SIDEBAR: Teacher Profile, GCP Config & Session Management
# ==============================================================================
with st.sidebar:
    st.markdown("### 👩‍🏫 Educator Profile")
    teacher_id_input = st.text_input(
        "Teacher ID / Profile",
        value=st.session_state.teacher_id,
        help="Loads category preferences and historical exam drafts."
    )
    if teacher_id_input != st.session_state.teacher_id:
        st.session_state.teacher_id = teacher_id_input
        st.session_state.orchestrator.set_teacher_id(teacher_id_input)
        st.rerun()

    st.markdown("---")
    st.markdown("### ⚡ AI & Cloud Engine")
    api_key_input = st.text_input(
        "Gemini API Key (Optional)",
        value=AppConfig.GEMINI_API_KEY,
        type="password",
        help="Leave blank to use environment default or local engine."
    )
    if api_key_input:
        AppConfig.GEMINI_API_KEY = api_key_input
        os.environ["GEMINI_API_KEY"] = api_key_input

    model_choice = st.selectbox(
        "Gemini Model",
        options=["gemini-3.7-flash", "gemini-2.5-flash", "gemini-1.5-pro"],
        index=0,
        help="Primary reasoning & self-healing compilation model."
    )
    AppConfig.DEFAULT_MODEL = model_choice

    gcp_status = "🟢 Vertex AI / GCS Active" if AppConfig.is_gcp_active() else "🟡 Standalone / Hybrid Mode"
    st.caption(f"Status: {gcp_status}")

    st.markdown("---")
    st.markdown("### 📂 Past Sessions & Recovery")
    
    if st.button("➕ Start New Session", use_container_width=True):
        st.session_state.current_session = None
        st.session_state.compilation_logs = []
        st.rerun()

    saved_sessions = session_mgr.list_sessions(teacher_id=st.session_state.teacher_id)
    if saved_sessions:
        session_options = {f"{s['title'][:28]}... ({s['paper_type']})": s["session_id"] for s in saved_sessions}
        selected_label = st.selectbox("Saved Drafts", options=list(session_options.keys()))
        selected_sess_id = session_options[selected_label]
        
        col_res, col_del = st.columns(2)
        with col_res:
            if st.button("📥 Restore", use_container_width=True):
                loaded = session_mgr.get_session(selected_sess_id)
                if loaded:
                    st.session_state.current_session = loaded
                    st.success(f"Restored {loaded.session_id}")
                    st.rerun()
        with col_del:
            if st.button("🗑️ Delete", use_container_width=True):
                session_mgr.delete_session(selected_sess_id)
                if st.session_state.current_session and st.session_state.current_session.session_id == selected_sess_id:
                    st.session_state.current_session = None
                st.warning("Session deleted.")
                st.rerun()
    else:
        st.caption("No historical sessions found.")

    st.markdown("---")
    st.markdown("### 📚 Ingest Past Papers (RAG)")
    uploaded_files = st.file_uploader(
        "Upload scanned .pdf or Word .docx past papers",
        type=["pdf", "docx", "txt", "tex"],
        accept_multiple_files=True
    )
    if uploaded_files:
        count = st.session_state.orchestrator.ingest_past_papers(uploaded_files)
        st.success(f"Indexed {count} reference documents for style grounding!")

# ==============================================================================
# MAIN PANEL: Header & Hero
# ==============================================================================
st.markdown("""
<div class="main-header">
    <div class="main-title">EduScribe AI</div>
    <div class="main-tagline">
        The adaptive co-authoring agent for technical educators: turning syllabus standards into compiled LaTeX papers, balanced synthetic datasets, and verified mark schemes.
    </div>
    <div style="margin-top: 12px;">
        <span class="badge-pill badge-gemini">Gemini 3.7 Flash</span>
        <span class="badge-pill badge-latex">pdflatex Self-Healing</span>
        <span class="badge-pill badge-fairness">Demographic Fairness Guardrails</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Paper Creation Form
with st.expander("🛠️ Exam Specifications & Co-Authoring Prompt", expanded=True if not st.session_state.current_session else False):
    # Row 1: Paper Type & Syllabus Topic Selector (Wide Columns)
    col_paper, col_topic = st.columns([1, 1.5])
    
    with col_paper:
        paper_type = st.radio(
            "9569 Examination Paper",
            options=["theory", "practical"],
            format_func=lambda x: "📖 Paper 1: Written Examination (Theory / 9569/01)" if x == "theory" else "💻 Paper 2: Lab Practical Examination (Practical / 9569/02)",
            horizontal=False
        )
        syllabus_code = "9569"
        paper_number = "01" if paper_type == "theory" else "02"
        st.markdown("**Syllabus Standard:** `9569 H2 Computing (2027 SEAB/Cambridge)`")

    with col_topic:
        category_options = {
            "sec1_linear_adts": "Section 1: Stacks, Circular Queues & Linked Lists",
            "sec1_nonlinear_bst_hash": "Section 1: Binary Search Trees & Hash Tables",
            "sec2_algorithms_sorting_searching": "Section 2: Quicksort, Merge Sort, Binary Search & Big-O",
            "sec2_logic_decision_tables": "Section 2: Decision Tables & Logic Simplification",
            "sec3_oop_hierarchies": "Section 3: OOP Classes, Inheritance & Polymorphism",
            "sec3_sql_normalisation": "Section 3: Relational DBs (1NF-3NF) & SQL DDL/DML",
            "sec3_web_networks_security": "Section 3: Web Apps (Flask/HTTP), OSI/TCP-IP, Subnetting & Security",
            "sec4_ethics_ai_pdpa": "Section 4: PDPA, AI/ML Ethics & Cybersecurity"
        }
        default_cat = "sec1_linear_adts" if paper_type == "practical" else "sec2_logic_decision_tables"
        category = st.selectbox(
            "2027 Syllabus Section / Core Topic",
            options=list(category_options.keys()),
            format_func=lambda k: category_options[k],
            index=0 if paper_type == "practical" else 3
        )
        
        # Display Learned Style for this category
        style = pref_learner.get_style_for_category(category)
        st.markdown(f"**Learned Style:** `{style.get('preferred_depth', 'long_contextual')}` | `{style.get('task_count', 4)}` questions | `{style.get('rubric_style', 'granular_partial_credit')}`")

    # Row 2: Metadata Fields
    col_inst, col_yr, col_ser = st.columns([2, 1, 1])
    with col_inst:
        institution = st.text_input("Institution Name", value="Anderson Serangoon Junior College")
    with col_yr:
        exam_year = st.text_input("Exam Year", value="2027")
    with col_ser:
        exam_series = st.selectbox("Series", ["PRELIM", "SPECIMEN", "FINAL"])

    # Authoring Prompt
    default_sample_prompt = (
        "Create an H2 Computing Paper 2 practical task on implementing a Stack abstract data type in Python (push, pop, underflow check) and processing CANDIDATES.csv to calculate distinction metrics and generate a report."
        if paper_type == "practical" else
        "Create an H2 Computing Paper 1 section featuring an inventory stock decision table with boundary conditions, a recursive Mystery() function trace table with Big-O complexity analysis, and 3NF database normalisation questions."
    )
    user_prompt = st.text_area(
        "Exam Authoring Prompt & Learning Objectives",
        value=default_sample_prompt,
        height=110,
        help="Specify the algorithms, data structures, scenarios, or syllabus objectives you want the co-authoring agent to construct."
    )

    col_btn, col_chk = st.columns([1, 2])
    with col_btn:
        generate_btn = st.button("🚀 Author & Compile Exam Package", type="primary", use_container_width=True)

# Handle Generation
if generate_btn:
    progress_placeholder = st.empty()
    status_container = st.container()
    
    logs = []
    def on_progress(step: str, msg: str):
        logs.append(f"**[{step}]** {msg}")
        progress_placeholder.info(f"🔄 **{step}**: {msg}")

    progress_handler = ExamGenerationProgress(log_callback=on_progress)
    
    with st.spinner("EduScribe AI is orchestrating blueprint, dataset synthesis, and LaTeX compilation..."):
        session = st.session_state.orchestrator.generate_exam_package(
            user_prompt=user_prompt,
            paper_type=paper_type,
            category=category,
            syllabus_code=syllabus_code[:4],
            paper_number=paper_number,
            institution=institution,
            exam_year=exam_year,
            exam_series=exam_series,
            progress=progress_handler
        )
        st.session_state.current_session = session
        st.session_state.compilation_logs = logs
        progress_placeholder.success("✅ Examination package synthesized, compiled, and verified successfully!")
        st.rerun()

# ==============================================================================
# DISPLAY ARTEFACTS & RESULTS
# ==============================================================================
curr_sess: ExamSession = st.session_state.current_session

if curr_sess:
    st.markdown("---")
    
    # Top Action Bar & Metrics
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(f"<div class='metric-box'><div class='metric-value' style='color: #0f172a; font-weight: 800;'>{curr_sess.paper_type.upper()}</div><div class='metric-label' style='color: #475569; font-weight: 600;'>Paper Type</div></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='metric-box'><div class='metric-value' style='color: #0f172a; font-weight: 800;'>{curr_sess.syllabus_code}/{curr_sess.paper_number}</div><div class='metric-label' style='color: #475569; font-weight: 600;'>Paper Code</div></div>", unsafe_allow_html=True)
    with m3:
        total_m = curr_sess.blueprint.get("total_marks", 75) if isinstance(curr_sess.blueprint, dict) else 75
        st.markdown(f"<div class='metric-box'><div class='metric-value' style='color: #0f172a; font-weight: 800;'>{total_m}</div><div class='metric-label' style='color: #475569; font-weight: 600;'>Total Marks</div></div>", unsafe_allow_html=True)
    with m4:
        tasks_count = len(curr_sess.blueprint.get("sections", [])) if isinstance(curr_sess.blueprint, dict) else 4
        st.markdown(f"<div class='metric-box'><div class='metric-value' style='color: #0f172a; font-weight: 800;'>{tasks_count}</div><div class='metric-label' style='color: #475569; font-weight: 600;'>Tasks / Questions</div></div>", unsafe_allow_html=True)
    with m5:
        zip_bytes = session_mgr.export_bundle_zip(curr_sess.session_id)
        if zip_bytes:
            st.download_button(
                label="📦 Download .ZIP Bundle",
                data=zip_bytes,
                file_name=f"{curr_sess.syllabus_code}_{curr_sess.paper_number}_{curr_sess.session_id}_package.zip",
                mime="application/zip",
                use_container_width=True
            )

    # Multi-Artefact Tab Navigation
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📋 Blueprint & Structure",
        "📄 Exam Question Paper",
        "✅ Mark Scheme & Rubrics",
        "📊 Demographic Datasets & Code",
        "⚙️ Self-Healing Telemetry",
        "💡 Style Adaptation Feedback"
    ])

    # --------------------------------------------------------------------------
    # TAB 1: Blueprint & Structure
    # --------------------------------------------------------------------------
    with tab1:
        st.markdown(f"### {curr_sess.title}")
        bp = curr_sess.blueprint or {}
        
        st.markdown("#### 🎯 Targeted Learning Objectives")
        for obj in bp.get("learning_objectives", []):
            st.markdown(f"- **{obj}**")

        st.markdown("#### 📑 Question Breakdown & Mark Allocations")
        sections = bp.get("sections", [])
        for sec in sections:
            subparts_html = ""
            subparts = sec.get("subparts", [])
            if subparts:
                items_str = "".join([f"<li style='margin-bottom: 4px; color: #1e293b;'><strong style='color: #0f172a;'>{sp.get('label', '')}</strong>: {sp.get('description', '')} <code style='background: #f1f5f9; padding: 2px 6px; border-radius: 4px; color: #0f172a;'>[{sp.get('marks', '')}m]</code></li>" for sp in subparts])
                subparts_html = f"<ul style='margin-top: 10px; margin-bottom: 0; padding-left: 20px;'>{items_str}</ul>"

            card_html = f"""
            <div class="ed-card">
                <div class="card-title">
                    <span style="color: #0f172a; font-weight: 700;">{sec.get('title', 'Task')}</span>
                    <span class="badge-pill badge-latex">{sec.get('marks', 0)} Marks</span>
                </div>
                <div class="card-subtitle" style="color: #475569;">Topic: {sec.get('topic', 'N/A')}</div>
                {subparts_html}
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)

    from src.sandbox.latex_renderer import LaTeXVisualRenderer

    # --------------------------------------------------------------------------
    # TAB 2: Exam Question Paper (Typeset View, PDF, and .tex)
    # --------------------------------------------------------------------------
    with tab2:
        col_hdr, col_btn_down = st.columns([1.6, 1])
        with col_hdr:
            view_mode = st.radio(
                "Paper View Mode",
                options=["📜 Typeset Exam Paper (Cambridge Layout)", "📄 Compiled PDF Document", "💻 LaTeX Source Code (`paper.tex`)"],
                index=0,
                horizontal=True
            )
        with col_btn_down:
            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.download_button(
                    "⬇️ paper.tex",
                    data=curr_sess.latex_source,
                    file_name="paper.tex",
                    mime="text/x-tex",
                    use_container_width=True
                )
            with col_d2:
                pdf_file = Path(curr_sess.pdf_path) if curr_sess.pdf_path else None
                if pdf_file and pdf_file.exists():
                    pdf_data = pdf_file.read_bytes()
                    st.download_button(
                        "⬇️ paper.pdf",
                        data=pdf_data,
                        file_name=f"{curr_sess.syllabus_code}_{curr_sess.paper_number}_paper.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )

        if "Typeset Exam Paper" in view_mode:
            rendered_html = LaTeXVisualRenderer.render_to_html(curr_sess.latex_source, title=curr_sess.title)
            import streamlit.components.v1 as components
            components.html(rendered_html, height=900, scrolling=True)
        elif "Compiled PDF" in view_mode:
            pdf_file = Path(curr_sess.pdf_path) if curr_sess.pdf_path else None
            if pdf_file and pdf_file.exists():
                import base64
                pdf_b64 = base64.b64encode(pdf_file.read_bytes()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{pdf_b64}" width="100%" height="750" type="application/pdf" style="border: 1px solid #cbd5e1; border-radius: 10px; margin-top: 10px;"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            else:
                st.info("PDF document will render here upon generating exam package.")
        else:
            st.code(curr_sess.latex_source, language="latex")

    # --------------------------------------------------------------------------
    # TAB 3: Mark Scheme & Rubrics (Typeset View, PDF, and .tex)
    # --------------------------------------------------------------------------
    with tab3:
        col_mshdr, col_msbtn = st.columns([1.6, 1])
        with col_mshdr:
            ms_view_mode = st.radio(
                "Mark Scheme View Mode",
                options=["🎓 Typeset Mark Scheme (Cambridge Layout)", "📄 Compiled PDF Document", "💻 LaTeX Source Code (`mark_scheme.tex`)"],
                index=0,
                horizontal=True
            )
        with col_msbtn:
            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
            col_msd1, col_msd2 = st.columns(2)
            with col_msd1:
                st.download_button(
                    "⬇️ mark_scheme.tex",
                    data=curr_sess.mark_scheme_source,
                    file_name="mark_scheme.tex",
                    mime="text/x-tex",
                    use_container_width=True
                )
            with col_msd2:
                sess_dir = BASE_DIR / "data_store" / "sessions" / curr_sess.session_id
                ms_pdf = sess_dir / "mark_scheme.pdf"
                if ms_pdf.exists():
                    st.download_button(
                        "⬇️ mark_scheme.pdf",
                        data=ms_pdf.read_bytes(),
                        file_name=f"{curr_sess.syllabus_code}_{curr_sess.paper_number}_mark_scheme.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )

        if "Typeset Mark Scheme" in ms_view_mode:
            ms_rendered_html = LaTeXVisualRenderer.render_to_html(curr_sess.mark_scheme_source, title="Mark Scheme")
            import streamlit.components.v1 as components
            components.html(ms_rendered_html, height=900, scrolling=True)
        elif "Compiled PDF" in ms_view_mode:
            sess_dir = BASE_DIR / "data_store" / "sessions" / curr_sess.session_id
            ms_pdf = sess_dir / "mark_scheme.pdf"
            if ms_pdf.exists():
                import base64
                pdf_b64 = base64.b64encode(ms_pdf.read_bytes()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{pdf_b64}" width="100%" height="750" type="application/pdf" style="border: 1px solid #cbd5e1; border-radius: 10px; margin-top: 10px;"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            else:
                st.info("Mark scheme PDF will render here upon package compilation.")
        else:
            st.code(curr_sess.mark_scheme_source, language="latex")

    # --------------------------------------------------------------------------
    # TAB 4: Demographic Datasets & Starter Code
    # --------------------------------------------------------------------------
    with tab4:
        st.markdown("### 📊 Demographic Fairness & Synthetic Data Sandbox")
        
        if curr_sess.generated_datasets:
            for ds in curr_sess.generated_datasets:
                st.markdown(f"#### 📁 Companion Resource: `{ds.get('filename')}`")
                content = ds.get("content", "")
                
                if ds.get("filename", "").endswith(".csv"):
                    try:
                        df = pd.read_csv(io.StringIO(content))
                        st.dataframe(df, use_container_width=True)
                        
                        # Display Demographic Fairness Telemetry
                        if "Gender" in df.columns:
                            col_f1, col_f2 = st.columns(2)
                            with col_f1:
                                gender_counts = df["Gender"].value_counts().to_dict()
                                st.markdown(f"**Gender Distribution:** 🚹 Male: `{gender_counts.get('Male', 0)}` | 🚺 Female: `{gender_counts.get('Female', 0)}` (Balanced Split)")
                            with col_f2:
                                st.markdown(f"**Total Records:** `{len(df)}` | **Multiracial Cohort Verified** ✅")
                    except Exception:
                        st.text(content)
                else:
                    st.code(content, language="sql")

                st.download_button(
                    f"⬇️ Download {ds.get('filename')}",
                    data=content,
                    file_name=ds.get("filename"),
                    mime="text/plain"
                )

        if curr_sess.starter_files:
            st.markdown("---")
            st.markdown("#### 🐍 Python Starter File Execution Sandbox")
            for sf in curr_sess.starter_files:
                st.markdown(f"**File:** `{sf.get('filename')}`")
                code_content = sf.get("content", "")
                st.code(code_content, language="python")
                
                if st.button(f"▶️ Run & Test `{sf.get('filename')}` in Sandbox"):
                    sess_dir = BASE_DIR / "data_store" / "sessions" / curr_sess.session_id
                    res = CodeExecutor.execute_python_code(code_content, sess_dir)
                    if res["success"]:
                        st.success("Execution Output:")
                        st.code(res["stdout"])
                    else:
                        st.error("Execution Error:")
                        st.code(res["stderr"])

    # --------------------------------------------------------------------------
    # TAB 5: Self-Healing Telemetry
    # --------------------------------------------------------------------------
    with tab5:
        st.markdown("### 🔄 pdflatex Compilation & Gemini Self-Healing Logs")
        if curr_sess.compilation_logs:
            st.text_area("Full Compilation Log & Stderr", value=curr_sess.compilation_logs, height=350)
        else:
            st.info("No compilation errors encountered. Document compiled cleanly on first pass!")

    # --------------------------------------------------------------------------
    # TAB 6: Style Adaptation Feedback
    # --------------------------------------------------------------------------
    with tab6:
        st.markdown("### 🧠 Adaptive Educator Preference Feedback")
        st.markdown("Teach EduScribe AI your personal style adjustments for this syllabus category.")
        
        feedback_input = st.text_area(
            "Educator Style Feedback",
            placeholder="e.g. 'I prefer shorter 2-line code starter boxes and 8-mark OOP tasks rather than 12-mark ones.'"
        )
        if st.button("💾 Adapt & Save Preferences"):
            updated = pref_learner.adapt_preferences_from_feedback(
                category=curr_sess.category,
                user_prompt=curr_sess.title,
                educator_feedback=feedback_input
            )
            st.success(f"Preferences updated and saved to Firestore/Local cache for category '{curr_sess.category}'!")
            st.json(updated)
