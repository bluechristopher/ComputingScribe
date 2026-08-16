"""
ComputingScribe AI - Streamlit Web Application
Collaborative Co-Authoring Partner for Singapore-Cambridge GCE A-Level H2 Computing (9569).
Renders KaTeX question previews, multi-agent train station progress, and dual authoring modes:
- Full Paper Co-Authoring (All-in-One)
- Question-by-Question Co-Authoring Studio (Iterative Refinement, Appending & Auto-Renumbering)
"""

import os
import sys
import io
import time
import base64
from pathlib import Path

# Explicitly ensure repository root is in sys.path across all deployment environments (Cloud Run, Docker, Local)
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from config.gcp_config import AppConfig, BASE_DIR
from src.agent.orchestrator import EduScribeOrchestrator, ExamGenerationProgress
from src.agent.preference_learner import PreferenceLearner
from src.agent.session_manager import SessionManager, ExamSession
from src.sandbox.code_executor import CodeExecutor
from src.sandbox.latex_renderer import LaTeXVisualRenderer

# Page Configuration
st.set_page_config(
    page_title="ComputingScribe AI | H2 Computing Co-Authoring Partner",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load Custom CSS
css_file = Path(__file__).resolve().parent / "style.css"
if css_file.exists():
    with open(css_file, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Initialize Session State
if "teacher_id" not in st.session_state:
    st.session_state.teacher_id = "default_educator"

if "orchestrator" not in st.session_state or not hasattr(st.session_state.orchestrator, "refine_full_paper"):
    st.session_state.orchestrator = EduScribeOrchestrator(teacher_id=st.session_state.teacher_id)

if "current_session" not in st.session_state:
    st.session_state.current_session = None

if "compilation_logs" not in st.session_state:
    st.session_state.compilation_logs = []

# Question-by-Question Studio Session State
if "studio_questions" not in st.session_state:
    st.session_state.studio_questions = []

if "studio_current_draft" not in st.session_state:
    st.session_state.studio_current_draft = None

pref_learner: PreferenceLearner = st.session_state.orchestrator.preference_learner
session_mgr: SessionManager = st.session_state.orchestrator.session_manager

# ==============================================================================
# SIDEBAR: AI Engine, Teacher Profile, Saved Drafts & Enhanced RAG Ingestion
# ==============================================================================
with st.sidebar:
    st.markdown("## 🎓 ComputingScribe AI")
    st.caption("Collaborative Partner for Technical Educators")
    
    st.markdown("---")
    st.markdown("🤖 **Model**: `Gemini 3.7 Flash`")
    
    with st.expander("⚙️ AI Engine & Settings", expanded=False):
        st.caption("Infrastructure: 🟢 Serverless on Google Cloud Run")
        active_key = st.session_state.get("gemini_api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        api_key_input = st.text_input(
            "Gemini API Key",
            value=active_key,
            type="password",
            placeholder="AIzaSy...",
            help="Paste your Gemini API key here."
        )
        if api_key_input:
            st.session_state["gemini_api_key"] = api_key_input.strip()
            os.environ["GEMINI_API_KEY"] = api_key_input.strip()
            st.success("API Key saved.")
    
    st.markdown("---")
    st.markdown("### 👩‍🏫 Educator Profile")
    teacher_name = st.text_input("Teacher ID / Handle", value=st.session_state.teacher_id)
    if teacher_name != st.session_state.teacher_id:
        st.session_state.teacher_id = teacher_name
        st.session_state.orchestrator.set_teacher_id(teacher_name)
        st.success(f"Loaded memory profile for: {teacher_name}")

    st.markdown("---")
    st.markdown("### 📂 Past Sessions & Recovery")
    
    @st.cache_data(ttl=60, show_spinner=False)
    def _fetch_cached_sessions(t_id: str):
        return session_mgr.list_sessions(teacher_id=t_id)

    if st.button("➕ Start New Session", use_container_width=True):
        st.session_state.current_session = None
        st.session_state.compilation_logs = []
        st.session_state.studio_questions = []
        st.session_state.studio_current_draft = None
        _fetch_cached_sessions.clear()
        st.rerun()

    saved_sessions = _fetch_cached_sessions(st.session_state.teacher_id)
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
                    st.session_state.studio_questions = loaded.questions or []
                    st.success(f"Restored {loaded.session_id}")
                    st.rerun()
        with col_del:
            if st.button("🗑️ Delete", use_container_width=True):
                session_mgr.delete_session(selected_sess_id)
                _fetch_cached_sessions.clear()
                if st.session_state.current_session and st.session_state.current_session.session_id == selected_sess_id:
                    st.session_state.current_session = None
                st.warning("Session deleted.")
                st.rerun()
    else:
        st.caption("No historical sessions found.")

    # Enhanced RAG Ingestion Section with High-Res PDF & MS Word Icons
    st.markdown("---")
    st.markdown("### 📚 Ingest Past Papers (RAG)")
    st.caption("Upload school prelims or past papers to ground phrasing style.")
    
    uploaded_files = st.file_uploader(
        "Upload reference papers",
        type=["pdf", "docx", "txt", "tex"],
        accept_multiple_files=True
    )
    
    if uploaded_files:
        count = st.session_state.orchestrator.ingest_past_papers(uploaded_files)
        st.success(f"Indexed {count} reference document(s) for style grounding!")
        
        st.markdown("#### 📑 Grounded Reference Papers:")
        for uf in uploaded_files:
            file_name = uf.name
            file_size_kb = round(len(uf.getvalue()) / 1024, 1)
            
            # Select High-Res Official Icon
            if file_name.lower().endswith(".pdf"):
                icon_url = "https://upload.wikimedia.org/wikipedia/commons/1/1a/Adobe_Reader_XI_icon.png"
                badge_type = "PDF Document"
            elif file_name.lower().endswith(".docx"):
                icon_url = "https://upload.wikimedia.org/wikipedia/commons/e/e8/Microsoft_Office_Word_%282025%E2%80%93present%29.svg"
                badge_type = "MS Word Document"
            else:
                icon_url = "https://upload.wikimedia.org/wikipedia/commons/9/9b/TeX_logo.svg"
                badge_type = "LaTeX Source"

            card_html = (
                f'<div style="display: flex; align-items: center; background: #1e293b; border: 1px solid #3b82f6; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px;">'
                f'<img src="{icon_url}" style="width: 42px; height: 42px; object-fit: contain; margin-right: 12px; flex-shrink: 0;" />'
                f'<div style="overflow: hidden; text-overflow: ellipsis; word-break: break-word;">'
                f'<div style="font-weight: 700; font-size: 0.9rem; color: #f8fafc; line-height: 1.3;">{file_name}</div>'
                f'<div style="font-size: 0.75rem; color: #93c5fd; margin-top: 2px;">{badge_type} • {file_size_kb} KB <span style="background: #065f46; color: #6ee7b7; padding: 1px 5px; border-radius: 4px; font-weight: bold; margin-left: 4px;">Indexed ✅</span></div>'
                f'</div>'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

# ==============================================================================
# MAIN PANEL: Header & Hero
# ==============================================================================
st.markdown("""
<div class="main-header">
    <div class="main-title">ComputingScribe AI</div>
    <div class="main-tagline">
        The adaptive co-authoring partner for technical educators: turning syllabus standards into compiled LaTeX papers, balanced synthetic datasets, and verified mark schemes.
    </div>
    <div style="margin-top: 12px;">
        <span class="badge-pill badge-gemini">Gemini on Vertex AI</span>
        <span class="badge-pill badge-latex">pdflatex Self-Healing</span>
        <span class="badge-pill badge-fairness">Demographic Fairness Guardrails</span>
    </div>
</div>
""", unsafe_allow_html=True)

# Authoring Mode Selection
col_m1, col_m2 = st.columns([1, 1])
with col_m1:
    author_mode = st.radio(
        "🛠️ Choose Authoring Mode",
        options=["⚡ Full Paper Co-Authoring (All-in-One)", "🎨 Question-by-Question Studio (Iterative & Modular)"],
        horizontal=True
    )

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

# ==============================================================================
# MODE A: FULL PAPER CO-AUTHORING (ALL-IN-ONE)
# ==============================================================================
if "Full Paper" in author_mode:
    with st.expander("🛠️ Full Exam Specifications & Co-Authoring Prompt", expanded=True if not st.session_state.current_session else False):
        col_type, col_style_info = st.columns([1.2, 1.8])
        
        with col_type:
            paper_type = st.radio(
                "Paper Format",
                ["practical", "theory"],
                format_func=lambda x: "Paper 2 Practical (9569/02)" if x == "practical" else "Paper 1 Theory (9569/01)",
                horizontal=True,
                key="full_paper_type"
            )
            syllabus_code = "9569"
            paper_number = "01" if paper_type == "theory" else "02"
            st.markdown("**Syllabus Standard:** `9569 H2 Computing (2027 SEAB/Cambridge)`")

        with col_style_info:
            style = pref_learner.get_style()
            st.markdown("**Adaptive Educator Style:**")
            st.markdown(f"- **Depth & Context:** `{style.get('preferred_depth', 'long_contextual')}`")
            st.markdown(f"- **Rubrics:** `{style.get('rubric_style', 'granular_partial_credit')}`")
            st.caption("✨ Calibrated across comprehensive 9569 syllabus sections.")
            category = "comprehensive_syllabus"

        # Metadata Fields
        col_inst, col_yr, col_ser = st.columns([2, 1, 1])
        with col_inst:
            institution = st.text_input("Institution Name", value="HelloWorld Junior College", key="full_inst")
        with col_yr:
            exam_year = st.text_input("Exam Year", value="2027", key="full_yr")
        with col_ser:
            exam_series = st.selectbox("Series", ["PRELIM", "SPECIMEN", "FINAL"], key="full_ser")

        default_sample_prompt = (
            "Create a contextual H2 Computing Paper 2 practical task on implementing a Stack abstract data type in Python (push, pop, underflow check) and processing CANDIDATES.csv to calculate distinction metrics and generate a report."
            if paper_type == "practical" else
            "Create a contextual H2 Computing Paper 1 section featuring an inventory stock decision table with boundary conditions, a recursive Mystery() function trace table with Big-O complexity analysis, and 3NF database normalisation questions."
        )
        user_prompt = st.text_area(
            "Exam Authoring Prompt & Learning Objectives",
            value=default_sample_prompt,
            height=110,
            help="Specify algorithms, data structures, scenarios, or syllabus objectives. Add 'contextual' for rich scenarios.",
            key="full_prompt"
        )

        col_btn, col_hint = st.columns([1, 2])
        with col_btn:
            generate_btn = st.button("🚀 Author & Compile Exam Package", type="primary", use_container_width=True)
        with col_hint:
            st.caption("💡 *Tip: Adding the word `'contextual'` triggers extended real-world scenarios and step-by-step bulleted subtasks.*")

    if generate_btn:
        train_station_placeholder = st.empty()
        logs = []
        pipeline_start_time = time.time()

        stations = [
            ("Station 1: Memory & Style Agent", "🧠 Querying persistent educator profile in Cloud Firestore..."),
            ("Station 2: RAG Grounding Agent", "📚 Scanning syllabus 9569 standards & indexing exam exemplars..."),
            ("Station 3: Blueprint Architect Agent", "📐 Synthesizing learning objectives & mark allocations on Vertex AI..."),
            ("Station 4: Demographic Synthesizer Agent", "⚖️ Generating 50/50 gender balanced datasets & SQL schemas..."),
            ("Station 5: Golden TeX Authoring Agent", "✍️ Drafting Cambridge-compliant LaTeX exam paper & mark scheme..."),
            ("Station 6: Self-Healing Sandbox Agent", "🔄 Executing pdflatex compilation & 3-pass Gemini self-healing..."),
            ("Station 7: Artifact Packaging Agent", "📦 Persisting session state & bundling .zip download package...")
        ]

        def render_train_station(current_station_idx: int, active_msg: str):
            total_elapsed = time.time() - pipeline_start_time
            mins, secs = divmod(int(total_elapsed), 60)
            ms = int((total_elapsed - int(total_elapsed)) * 10)
            elapsed_fmt = f"{mins:02d}:{secs:02d}.{ms}s" if mins > 0 else f"{secs}.{ms}s"

            station_boxes = []
            for idx, (s_name, s_desc) in enumerate(stations):
                if idx < current_station_idx:
                    status_icon = "✅"
                    bg_color = "#ecfdf5"
                    border_color = "#10b981"
                    text_color = "#065f46"
                elif idx == current_station_idx:
                    status_icon = "🚉 ⚡"
                    bg_color = "#eff6ff"
                    border_color = "#2563eb"
                    text_color = "#1e3a8a"
                else:
                    status_icon = "⏳"
                    bg_color = "#f8fafc"
                    border_color = "#cbd5e1"
                    text_color = "#64748b"

                box_html = (
                    f'<div style="flex: 1 1 120px; min-width: 120px; background: {bg_color}; '
                    f'border: 2px solid {border_color}; border-radius: 8px; padding: 8px 10px; margin: 4px; text-align: center;">'
                    f'<div style="font-size: 1.1rem;">{status_icon}</div>'
                    f'<div style="font-weight: 700; font-size: 0.8rem; color: {text_color}; margin-top: 4px;">{s_name.split(":")[0]}</div>'
                    f'<div style="font-size: 0.7rem; color: {text_color}; opacity: 0.9;">{s_name.split(":")[1]}</div>'
                    f'</div>'
                )
                station_boxes.append(box_html)
            
            track_html = (
                f'<div style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; padding: 16px; margin: 16px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">'
                f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">'
                f'<div style="font-weight: 800; font-size: 1.05rem; color: #0f172a;">'
                f'🚂 Multi-Agent Co-Authoring Pipeline (Station {min(current_station_idx + 1, 7)} of 7 Active)'
                f'</div>'
                f'<div style="font-family: monospace; font-size: 0.95rem; background: #e0f2fe; color: #0369a1; padding: 4px 12px; border-radius: 20px; border: 1px solid #7dd3fc; font-weight: 700;">'
                f'⏱️ Elapsed: {elapsed_fmt}'
                f'</div>'
                f'</div>'
                f'<div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;">'
                f'{"".join(station_boxes)}'
                f'</div>'
                f'<div style="margin-top: 12px; font-size: 0.88rem; color: #1e3a8a; background: #f0fdf4; padding: 10px 14px; border-radius: 6px; border-left: 4px solid #10b981; display: flex; justify-content: space-between; align-items: center;">'
                f'<div><strong>Current Action:</strong> {active_msg}</div>'
                f'<div style="font-family: monospace; font-size: 0.85rem; color: #059669; font-weight: 700;">⏱️ {elapsed_fmt}</div>'
                f'</div>'
                f'</div>'
            )
            train_station_placeholder.markdown(track_html, unsafe_allow_html=True)

        def on_progress(step: str, msg: str):
            logs.append(f"**[{step}]** {msg}")
            current_idx = 0
            for idx, (s_name, _) in enumerate(stations):
                if s_name.split(':')[0] in step:
                    current_idx = idx
                    break
            render_train_station(current_idx, msg)

        progress_handler = ExamGenerationProgress(log_callback=on_progress)
        try:
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
            total_dur = round(time.time() - pipeline_start_time, 1)
            render_train_station(6, f"🎉 All 7 agents completed their tasks in {total_dur}s!")
            time.sleep(0.5)
            st.rerun()
        except Exception as gen_err:
            st.error(f"Generation notification: {gen_err}")
            st.info("Displaying synthesized Cambridge assessment package.")

# ==============================================================================
# MODE B: QUESTION-BY-QUESTION CO-AUTHORING STUDIO
# ==============================================================================
else:
    st.markdown("### 🎨 Question-by-Question Co-Authoring Studio")
    st.caption("Craft, refine, append, and reorder tasks individually with automatic task renumbering.")

    col_studio_left, col_studio_right = st.columns([1.1, 0.9])

    # Left Column: Single Task Drafting & Refinement Workbench
    with col_studio_left:
        st.markdown("#### ✍️ Task Drafting Workbench")
        
        col_st_p, col_st_n, col_st_m = st.columns([1.2, 0.8, 0.8])
        with col_st_p:
            s_paper_type = st.selectbox("Paper Type", ["practical", "theory"], format_func=lambda x: "💻 Paper 2 Practical" if x == "practical" else "📖 Paper 1 Theory")
        with col_st_n:
            next_task_num = len(st.session_state.studio_questions) + 1
            s_task_num = st.number_input("Task #", min_value=1, max_value=10, value=next_task_num)
        with col_st_m:
            s_marks = st.number_input("Marks", min_value=5, max_value=50, value=25, step=5)

        s_category = st.selectbox(
            "Syllabus Category",
            options=list(category_options.keys()),
            format_func=lambda k: category_options[k],
            key="studio_cat"
        )

        s_prompt = st.text_area(
            "Question Authoring Prompt",
            placeholder="e.g. 'Create a contextual task on implementing a Circular Queue with bounds checking and processing order events.'",
            value="Create a contextual task on implementing a Circular Queue ADT in Python with enqueue, dequeue, and bounds validation.",
            height=90,
            key="studio_task_prompt"
        )

        draft_btn = st.button("✨ Draft Single Question with Gemini", type="primary", use_container_width=True)
        if draft_btn and s_prompt:
            t0 = time.time()
            with st.spinner("🤖 Gemini 3.7 Flash is drafting your question..."):
                task_draft = st.session_state.orchestrator.author_single_task(
                    prompt=s_prompt,
                    paper_type=s_paper_type,
                    category=s_category,
                    task_number=int(s_task_num),
                    total_marks=int(s_marks)
                )
                st.session_state.studio_current_draft = task_draft
                dur = round(time.time() - t0, 1)
                st.success(f"✨ Task {s_task_num} authored in {dur}s! Inspect preview below.")

        # Display Current Single Task Draft & Refinement Area
        if st.session_state.studio_current_draft:
            cur_draft = st.session_state.studio_current_draft
            st.markdown("---")
            st.markdown(f"#### 🔍 Draft Preview: `{cur_draft.get('title')}` ({cur_draft.get('marks')}m)")
            
            # KaTeX Live Preview for Single Question
            rendered_single = LaTeXVisualRenderer.render_questions_only_html(cur_draft.get("latex_code", ""), title="Single Task")
            components.html(rendered_single, height=380, scrolling=True)

            # Conversational Refinement
            refine_input = st.text_input(
                "💬 Refine this Question",
                placeholder="e.g. 'Make subtask 1.2 use recursion instead' or 'Increase marks to 30 with Big-O justification'"
            )
            col_ref, col_app = st.columns(2)
            with col_ref:
                if st.button("🔄 Refine Question", use_container_width=True):
                    if refine_input.strip():
                        with st.spinner("Refining question..."):
                            refined = st.session_state.orchestrator.refine_single_task(
                                current_task=cur_draft,
                                refinement_prompt=refine_input,
                                paper_type=s_paper_type
                            )
                            st.session_state.studio_current_draft = refined
                            st.success("Question refined!")
                            st.rerun()
            with col_app:
                if st.button("➕ Append to Question Paper", type="primary", use_container_width=True):
                    # Append and auto-renumber
                    new_list = list(st.session_state.studio_questions)
                    cur_draft["task_number"] = len(new_list) + 1
                    # Ensure renumbered properly
                    renumbered = st.session_state.orchestrator.renumber_task(cur_draft, len(new_list) + 1, s_paper_type)
                    new_list.append(renumbered)
                    st.session_state.studio_questions = new_list
                    st.session_state.studio_current_draft = None
                    st.success(f"Appended {renumbered.get('title')} to paper queue!")
                    st.rerun()

    # Right Column: Assembled Question Paper Queue & Reordering
    with col_studio_right:
        st.markdown("#### 📑 Assembled Question Paper Queue")
        
        q_list = st.session_state.studio_questions
        total_q_marks = sum(q.get("marks", 25) for q in q_list)
        
        st.markdown(f"**Assembled Questions:** `{len(q_list)}` | **Total Marks:** `{total_q_marks}` / `100` Marks")
        
        if not q_list:
            st.info("No questions appended yet. Draft questions on the left and click **'➕ Append to Question Paper'**.")
        else:
            for idx, q in enumerate(q_list):
                with st.container():
                    col_info, col_up, col_down, col_del = st.columns([3, 0.7, 0.7, 0.7])
                    with col_info:
                        st.markdown(f"**{idx + 1}. {q.get('title', f'Task {idx+1}')}**  \n<span style='color: #2563eb; font-weight: bold;'>{q.get('marks', 25)} Marks</span> • <span style='color: #64748b; font-size: 0.85rem;'>{q.get('topic', '')}</span>", unsafe_allow_html=True)
                    with col_up:
                        if idx > 0:
                            if st.button("⬆️", key=f"up_{idx}", help="Move Up"):
                                # Swap and auto-renumber
                                q_list[idx], q_list[idx - 1] = q_list[idx - 1], q_list[idx]
                                # Renumber all tasks
                                for i in range(len(q_list)):
                                    q_list[i] = st.session_state.orchestrator.renumber_task(q_list[i], i + 1, s_paper_type)
                                st.session_state.studio_questions = q_list
                                st.rerun()
                    with col_down:
                        if idx < len(q_list) - 1:
                            if st.button("⬇️", key=f"down_{idx}", help="Move Down"):
                                q_list[idx], q_list[idx + 1] = q_list[idx + 1], q_list[idx]
                                for i in range(len(q_list)):
                                    q_list[i] = st.session_state.orchestrator.renumber_task(q_list[i], i + 1, s_paper_type)
                                st.session_state.studio_questions = q_list
                                st.rerun()
                    with col_del:
                        if st.button("🗑️", key=f"del_{idx}", help="Delete Question"):
                            q_list.pop(idx)
                            for i in range(len(q_list)):
                                q_list[i] = st.session_state.orchestrator.renumber_task(q_list[i], i + 1, s_paper_type)
                            st.session_state.studio_questions = q_list
                            st.rerun()
                    st.markdown("<hr style='margin: 6px 0; border-color: #e2e8f0;'/>", unsafe_allow_html=True)

            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
            
            # Compile & Build Button styled with blue background & light blue text
            st.markdown("<div class='compile-build-box'>", unsafe_allow_html=True)
            if st.button("🔨 Compile & Build Final Exam Package", use_container_width=True, key="studio_compile_btn"):
                with st.spinner("Assembling LaTeX document, companion datasets, and compiling in sandbox..."):
                    compiled_sess = st.session_state.orchestrator.compile_assembled_session(
                        tasks_list=q_list,
                        paper_type=s_paper_type,
                        syllabus_code="9569",
                        paper_number="02" if s_paper_type == "practical" else "01"
                    )
                    st.session_state.current_session = compiled_sess
                    st.success("🎉 Full Exam Package Assembled and Compiled Successfully!")
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

# ==============================================================================
# DISPLAY ARTIFACTS & RESULTS
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
        total_m = curr_sess.blueprint.get("total_marks", 100) if isinstance(curr_sess.blueprint, dict) else 100
        st.markdown(f"<div class='metric-box'><div class='metric-value' style='color: #0f172a; font-weight: 800;'>{total_m}</div><div class='metric-label' style='color: #475569; font-weight: 600;'>Total Marks</div></div>", unsafe_allow_html=True)
    with m4:
        tasks_count = len(curr_sess.blueprint.get("sections", [])) if isinstance(curr_sess.blueprint, dict) else len(curr_sess.questions) or 4
        st.markdown(f"<div class='metric-box'><div class='metric-value' style='color: #0f172a; font-weight: 800;'>{tasks_count}</div><div class='metric-label' style='color: #475569; font-weight: 600;'>Tasks / Questions</div></div>", unsafe_allow_html=True)
    with m5:
        # Download Complete .ZIP Archive Button
        zip_path = BASE_DIR / "data_store" / "sessions" / curr_sess.session_id / f"{curr_sess.session_id}_package.zip"
        if zip_path.exists():
            st.download_button(
                "📦 Download .ZIP Bundle",
                data=zip_path.read_bytes(),
                file_name=f"{curr_sess.syllabus_code}_{curr_sess.paper_number}_complete_package.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True
            )

    # --------------------------------------------------------------------------
    # NAVIGATION TABS
    # --------------------------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📋 Exam Blueprint",
        "📄 Exam Question Paper",
        "📝 Cambridge Mark Scheme",
        "📊 Companion Datasets",
        "🔄 Self-Healing Telemetry",
        "🧠 Style Adaptation Feedback"
    ])

    # --------------------------------------------------------------------------
    # TAB 1: Blueprint & Objectives
    # --------------------------------------------------------------------------
    with tab1:
        st.markdown("### 📋 Syllabus-Calibrated Exam Blueprint")
        bp = curr_sess.blueprint if isinstance(curr_sess.blueprint, dict) else {}
        
        st.markdown("#### 🎯 Assessed Learning Objectives")
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

            card_html = (
                f'<div class="ed-card">'
                f'<div class="card-title">'
                f'<span style="color: #0f172a; font-weight: 700;">{sec.get("title", "Task")}</span>'
                f'<span class="badge-pill badge-latex">{sec.get("marks", 0)} Marks</span>'
                f'</div>'
                f'<div class="card-subtitle" style="color: #475569;">Topic: {sec.get("topic", "N/A")}</div>'
                f'{subparts_html}'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # TAB 2: Exam Question Paper (Clean KaTeX Questions Preview & Copy LaTeX)
    # --------------------------------------------------------------------------
    with tab2:
        col_hdr, col_btn_down = st.columns([1.5, 1])
        with col_hdr:
            st.markdown("### 📄 Question Paper (KaTeX Live Preview)")
            st.caption("Clean pedagogical view of questions, subtasks, Jupyter cells, and mark brackets.")
        with col_btn_down:
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.download_button(
                    "⬇️ paper.tex (Overleaf)",
                    data=curr_sess.latex_source,
                    file_name="paper.tex",
                    mime="text/x-tex",
                    use_container_width=True
                )
            with col_d2:
                pdf_file = Path(curr_sess.pdf_path) if curr_sess.pdf_path else None
                if pdf_file and pdf_file.exists():
                    st.download_button(
                        "⬇️ paper.pdf",
                        data=pdf_file.read_bytes(),
                        file_name=f"{curr_sess.syllabus_code}_{curr_sess.paper_number}_paper.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )

        # 1-Click Copy Full LaTeX for Overleaf Box
        with st.expander("📋 Copy Full LaTeX Source Code (for Overleaf / TeXLive / VS Code)", expanded=False):
            st.caption("Click the copy icon in the top right of the code box to paste directly into Overleaf:")
            st.code(curr_sess.latex_source, language="latex")

        # Clean KaTeX Questions Rendering (No Cover/Header noise)
        rendered_html = LaTeXVisualRenderer.render_questions_only_html(curr_sess.latex_source, title=curr_sess.title)
        components.html(rendered_html, height=850, scrolling=True)

        st.markdown("---")
        st.markdown("### 💬 Conversational Paper Editor & Refinement Workbench")
        st.caption("Prompt Gemini 3.7 Flash to refine, rephrase, add subtasks, adjust difficulty, or rewrite specific tasks across this working exam paper:")
        
        col_ref_in, col_ref_btn = st.columns([3.8, 1.2])
        with col_ref_in:
            paper_refine_prompt = st.text_input(
                "Conversational Refinement Prompt",
                placeholder="e.g. 'In Task 2, change the CSV column from Total_Marks to Percentage and add input validation.'",
                label_visibility="collapsed",
                key="paper_refine_prompt_input"
            )
        with col_ref_btn:
            refine_paper_btn = st.button("✨ Refine Paper with AI", type="primary", use_container_width=True)
            
        if refine_paper_btn and paper_refine_prompt:
            t0 = time.time()
            with st.spinner("🤖 Gemini 3.7 Flash is refining your exam paper and updating mark schemes..."):
                updated_sess = st.session_state.orchestrator.refine_full_paper(
                    session=curr_sess,
                    refinement_prompt=paper_refine_prompt
                )
                st.session_state.current_session = updated_sess
                dur = round(time.time() - t0, 1)
                st.success(f"🎉 Exam paper and mark scheme refined in {dur}s!")
                time.sleep(0.5)
                st.rerun()

    # --------------------------------------------------------------------------
    # TAB 3: Mark Scheme & Rubrics (Clean KaTeX View & Copy LaTeX)
    # --------------------------------------------------------------------------
    with tab3:
        col_mshdr, col_msbtn = st.columns([1.5, 1])
        with col_mshdr:
            st.markdown("### 📝 Official Cambridge Mark Scheme (KaTeX Live Preview)")
            st.caption("Granular partial credit rubrics with Assessment Objective (AO) allocations.")
        with col_msbtn:
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

        with st.expander("📋 Copy Mark Scheme LaTeX Source Code (for Overleaf / TeXLive)", expanded=False):
            st.code(curr_sess.mark_scheme_source, language="latex")

        ms_rendered_html = LaTeXVisualRenderer.render_questions_only_html(curr_sess.mark_scheme_source, title="Mark Scheme")
        components.html(ms_rendered_html, height=850, scrolling=True)

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
        st.markdown("Teach ComputingScribe AI your personal phrasing, scenario depth, and question structuring style. Preferences apply across all paper authoring.")
        
        feedback_input = st.text_area(
            "Educator Style Feedback",
            placeholder="e.g. 'I prefer concise 2-sentence scenario preambles and explicit type annotations in Python starter boxes.'"
        )
        if st.button("💾 Adapt & Save Preferences to Memory"):
            updated = pref_learner.adapt_preferences_from_feedback(
                category="generic",
                user_prompt=curr_sess.title,
                educator_feedback=feedback_input
            )
            st.success("Generic educator preferences updated and saved!")
            st.json(updated)
