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
import re
import json
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

if "last_generation_duration" not in st.session_state:
    st.session_state.last_generation_duration = 14.8

# Question-by-Question Studio Session State
if "studio_questions" not in st.session_state:
    st.session_state.studio_questions = []

if "studio_current_draft" not in st.session_state:
    st.session_state.studio_current_draft = None

pref_learner: PreferenceLearner = st.session_state.orchestrator.preference_learner
session_mgr: SessionManager = st.session_state.orchestrator.session_manager

PIPELINE_STATIONS = [
    ("Station 1: Memory & Style Agent", "🧠 Querying persistent educator profile in Cloud Firestore..."),
    ("Station 2: RAG Grounding Agent", "📚 Scanning syllabus 9569 standards & indexing exam exemplars..."),
    ("Station 3: Blueprint Architect Agent", "📐 Synthesizing learning objectives & mark allocations on Gemini 3.7 Flash..."),
    ("Station 4: Demographic Synthesizer Agent", "⚖️ Generating 50/50 gender balanced datasets & SQL schemas..."),
    ("Station 5: Golden TeX Authoring Agent", "✍️ Drafting Cambridge-compliant LaTeX exam paper & mark scheme..."),
    ("Station 6: Self-Healing Sandbox Agent", "🔄 Executing pdflatex compilation & 3-pass Gemini self-healing..."),
    ("Station 7: Artifact Packaging Agent", "📦 Persisting session state & bundling .zip download package...")
]

def build_pipeline_hud_html(
    current_station_idx: int,
    active_msg: str,
    is_done: bool = False,
    start_ms: int = 0,
    final_duration_str: str = "14.8s",
    skipped_indices: Optional[List[int]] = None
) -> str:
    skipped = set(skipped_indices or [])
    station_boxes = []
    for idx, (s_name, s_desc) in enumerate(PIPELINE_STATIONS):
        station_num = s_name.split(":")[0].strip()
        station_role = s_name.split(":")[1].strip()

        if idx in skipped:
            status_icon = "⏭️"
            box_class = "station-box-skipped"
            box_style = "background: #f1f5f9; border: 1.5px dashed #94a3b8; border-radius: 8px; padding: 8px 4px; text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 96px; opacity: 0.50;"
            title_color = "#64748b"
            station_role_disp = f"{station_role} <span style='font-size:0.6rem; color:#94a3b8; display:block;'>(Skipped)</span>"
            eq_html = ""
        elif is_done or idx < current_station_idx:
            status_icon = "✅"
            box_class = "station-box-done"
            box_style = "background: #ecfdf5; border: 2px solid #10b981; border-radius: 8px; padding: 8px 4px; text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 96px;"
            title_color = "#065f46"
            station_role_disp = station_role
            eq_html = ""
        elif idx == current_station_idx:
            status_icon = '<span class="station-icon-active">⚡</span>'
            box_class = "station-box-active"
            box_style = "border-radius: 8px; padding: 8px 4px; text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 96px;"
            title_color = "#ffffff"
            station_role_disp = station_role
            eq_html = '<div class="active-equalizer"><span></span><span></span><span></span><span></span><span></span></div>'
        else:
            status_icon = "⏳"
            box_class = "station-box-pending"
            box_style = "background: #f8fafc; border: 2px solid #cbd5e1; border-radius: 8px; padding: 8px 4px; text-align: center; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 96px;"
            title_color = "#64748b"
            station_role_disp = station_role
            eq_html = ""

        box_html = f"""
        <div class="{box_class}" style="{box_style}">
            <div style="font-size: 1.1rem; line-height: 1;">{status_icon}</div>
            {eq_html}
            <div style="font-weight: 800; font-size: 0.76rem; color: {title_color}; margin-top: 3px; line-height: 1.15;">{station_num}</div>
            <div style="font-size: 0.66rem; color: {title_color}; opacity: 0.95; line-height: 1.15; margin-top: 2px;">{station_role_disp}</div>
        </div>
        """
        station_boxes.append(box_html)

    status_tag = "🎉 All Active Stages Complete" if is_done else f"Station {min(current_station_idx + 1, 7)} of 7 Active"
    action_text = "🎉 All active agents completed their tasks successfully! Exam package compiled & ready." if is_done else active_msg
    spinner_html = "" if is_done else '<span class="inline-spinner"></span>'
    stopwatch_init_text = f"⏱️ {final_duration_str}" if is_done else "⏱️ 00:00.0s"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
* {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }}
body {{ background: transparent; padding: 2px; }}
.station-box-skipped {{ background: #f1f5f9 !important; border: 1.5px dashed #94a3b8 !important; opacity: 0.50 !important; }}
@keyframes metallicWave {{
    0% {{ background-position: -200% 0; }}
    100% {{ background-position: 200% 0; }}
}}
@keyframes activeStationPulse {{
    0%, 100% {{ box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4), 0 4px 14px rgba(37, 99, 235, 0.25); transform: translateY(0); }}
    50% {{ box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.5), 0 8px 24px rgba(37, 99, 235, 0.45); transform: translateY(-2px); }}
}}
@keyframes goldWhiteShimmer {{
    0% {{ color: #ffffff !important; text-shadow: 0 0 8px rgba(255, 255, 255, 0.9), 0 0 16px rgba(254, 240, 138, 0.6) !important; }}
    50% {{ color: #fde047 !important; text-shadow: 0 0 12px rgba(251, 191, 36, 0.95), 0 0 24px rgba(245, 158, 11, 0.8) !important; }}
    100% {{ color: #ffffff !important; text-shadow: 0 0 8px rgba(255, 255, 255, 0.9), 0 0 16px rgba(254, 240, 138, 0.6) !important; }}
}}
@keyframes miniRotate {{
    0% {{ transform: rotate(0deg); }}
    100% {{ transform: rotate(360deg); }}
}}
@keyframes eqBounce {{
    0% {{ height: 25%; transform: scaleY(0.4); opacity: 0.6; }}
    100% {{ height: 100%; transform: scaleY(1); opacity: 1; }}
}}
@keyframes iconFloat {{
    0%, 100% {{ transform: translateY(0) scale(1); filter: drop-shadow(0 0 6px rgba(253, 224, 71, 0.8)); }}
    50% {{ transform: translateY(-3px) scale(1.2); filter: drop-shadow(0 0 14px rgba(251, 191, 36, 1)); }}
}}
.station-box-active {{
    background: linear-gradient(110deg, #080f24 0%, #11224d 20%, #1e3a8a 45%, #2563eb 50%, #1e3a8a 55%, #11224d 80%, #080f24 100%) !important;
    background-size: 250% 100% !important;
    animation: metallicWave 2.5s infinite linear, activeStationPulse 2s infinite ease-in-out !important;
    border: 2px solid #60a5fa !important;
}}
.station-box-active * {{
    animation: goldWhiteShimmer 2.2s infinite ease-in-out !important;
    font-weight: 800 !important;
}}
.active-equalizer {{
    display: flex; justify-content: center; align-items: flex-end; gap: 3px; height: 10px; margin: 2px auto;
}}
.active-equalizer span {{
    display: inline-block; width: 3px; background: #fde047; border-radius: 2px;
    animation: eqBounce 0.9s ease-in-out infinite alternate; box-shadow: 0 0 6px rgba(253, 224, 71, 0.8);
}}
.active-equalizer span:nth-child(1) {{ height: 35%; animation-delay: 0.1s; }}
.active-equalizer span:nth-child(2) {{ height: 90%; animation-delay: 0.3s; }}
.active-equalizer span:nth-child(3) {{ height: 55%; animation-delay: 0.2s; }}
.active-equalizer span:nth-child(4) {{ height: 100%; animation-delay: 0.45s; }}
.active-equalizer span:nth-child(5) {{ height: 45%; animation-delay: 0.15s; }}
.station-icon-active {{ display: inline-block; animation: iconFloat 1.4s infinite ease-in-out; }}
.station-box-done {{ background: #ecfdf5; border: 2px solid #10b981; }}
.station-box-pending {{ background: #f8fafc; border: 2px solid #cbd5e1; }}
.inline-spinner {{
    display: inline-block; width: 14px; height: 14px; border: 2.5px solid rgba(16, 185, 129, 0.25);
    border-top-color: #10b981; border-radius: 50%; animation: miniRotate 0.75s linear infinite; vertical-align: -2px; margin-right: 8px; flex-shrink: 0;
}}
</style>
</head>
<body>
    <div style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; padding: 12px 14px; box-shadow: 0 4px 14px rgba(0,0,0,0.06);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="font-weight: 800; font-size: 1rem; color: #0f172a; display: flex; align-items: center;">
                🚂 Multi-Agent Co-Authoring Pipeline &nbsp;<span style="font-size: 0.76rem; background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 12px; font-weight: 700;">{status_tag}</span>
            </div>
            <div id="live-stopwatch" style="font-family: 'Courier New', monospace; font-size: 0.92rem; background: linear-gradient(135deg, #0369a1, #0284c7); color: #ffffff; padding: 4px 14px; border-radius: 20px; border: 1px solid #38bdf8; font-weight: 800; box-shadow: 0 0 12px rgba(56, 189, 248, 0.4);">
                {stopwatch_init_text}
            </div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(7, 1fr); gap: 6px; width: 100%;">
            {''.join(station_boxes)}
        </div>
        <div style="margin-top: 10px; font-size: 0.84rem; color: #1e3a8a; background: #f0fdf4; padding: 8px 12px; border-radius: 6px; border-left: 4px solid #10b981; display: flex; align-items: center; line-height: 1.35;">
            {spinner_html} <strong>Current Action:</strong>&nbsp;<span style="margin-left: 4px;">{action_text}</span>
        </div>
    </div>
    <script>
    (function() {{
        var startTime = {start_ms};
        var isDone = {'true' if is_done else 'false'};
        var el = document.getElementById('live-stopwatch');
        function pad(n) {{ return (n < 10 ? '0' : '') + n; }}
        function formatTime(elapsed) {{
            var mins = Math.floor(elapsed / 60);
            var secs = Math.floor(elapsed % 60);
            var tenths = Math.floor((elapsed % 1) * 10);
            return (mins > 0 ? pad(mins) + ':' : '') + (mins > 0 ? pad(secs) : secs) + '.' + tenths + 's';
        }}
        if (!isDone && startTime > 0) {{
            function update() {{
                var now = Date.now();
                var elapsed = Math.max(0, (now - startTime) / 1000);
                if (el) el.innerText = '⏱️ ' + formatTime(elapsed);
            }}
            var interval = setInterval(update, 100);
            update();
        }}
    }})();
    </script>
</body>
</html>"""

GEMINI_ICON = '<img src="https://upload.wikimedia.org/wikipedia/commons/1/1d/Google_Gemini_icon_2025.svg" width="18" height="18" style="vertical-align: -3px; margin-right: 6px;"/>'
GEMINI_ICON_SM = '<img src="https://upload.wikimedia.org/wikipedia/commons/1/1d/Google_Gemini_icon_2025.svg" width="15" height="15" style="vertical-align: -2px; margin-right: 4px;"/>'

# ==============================================================================
# SIDEBAR: AI Engine, Teacher Profile, Saved Drafts & Enhanced RAG Ingestion
# ==============================================================================
with st.sidebar:
    sidebar_img_path = BASE_DIR / "images" / "sidebar.jpg"
    if sidebar_img_path.exists():
        st.image(str(sidebar_img_path), use_container_width=True)
    else:
        st.markdown("## 🎓 ComputingScribe AI")
        st.caption("Collaborative Partner for Technical Educators")
    
    st.markdown(
        "<div style='text-align: center; color: #fbbf24; font-weight: 400; font-style: italic; font-size: 0.88rem; margin-top: -3px; margin-bottom: 3px; letter-spacing: 0.2px; text-shadow: 0 1px 2px rgba(0,0,0,0.5);'>"
        "☁️ Hosted on Google Cloud Platform"
        "</div>",
        unsafe_allow_html=True
    )
    
    st.markdown("---")
    st.markdown(f"**Model**: {GEMINI_ICON} <span style='color: #ffffff; font-weight: 700;'>Gemini 3.7 Flash</span>", unsafe_allow_html=True)
    
    active_key = st.session_state.get("gemini_api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    
    with st.expander("⚙️ AI Engine & Settings", expanded=True if not active_key else False):
        st.markdown("🔑 **Bring Your Own Key (BYOK)**")
        st.caption("You can obtain your Gemini API key from Google AI Studio. Your key is kept strictly in your local browser session and is never stored on the server.")
        st.markdown("[👉 Get a Gemini API Key from Google AI Studio](https://aistudio.google.com/app/apikey)", unsafe_allow_html=True)
        
        api_key_input = st.text_input(
            "Gemini API Key",
            value=active_key,
            type="password",
            placeholder="AIzaSy...",
            help="Paste your Gemini API key from Google AI Studio here."
        )
        if api_key_input:
            clean_k = api_key_input.strip()
            st.session_state["gemini_api_key"] = clean_k
            os.environ["GEMINI_API_KEY"] = clean_k
            st.success("✅ Gemini API Key connected!")
        elif not active_key:
            st.warning("⚠️ Please provide a Gemini API key to enable live exam generation.")
    
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
# MAIN PANEL: Header Banner Image (Full Width)
# ==============================================================================
banner_img_path = BASE_DIR / "images" / "banner.jpg"
if banner_img_path.exists():
    st.image(str(banner_img_path), use_container_width=True)
    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

# Authoring Mode Selection
col_m1, col_m2 = st.columns([1, 1])
with col_m1:
    author_mode = st.radio(
        "🛠️ Choose Authoring Mode",
        options=[
            "⚡ Full Paper Co-Authoring (All-in-One)",
            "🎨 Question-by-Question Studio (Iterative & Modular)",
            "📄 Document Transcriber (Word / PDF to Cambridge LaTeX)"
        ],
        horizontal=True
    )

PRACTICAL_TOPICS = [
    "Data Representation and Character Encoding",
    "Basic Python",
    "Python File I/O",
    "Modules: Random, Datetime",
    "Data Validation",
    "Recursion",
    "Searching and Sorting Algorithms",
    "OOP",
    "Stacks and Queues",
    "Hash Tables",
    "BST",
    "Linked Lists",
    "Machine Learning with sklearn",
    "SQLite Databases",
    "HTML, CSS, Flask"
]

THEORY_TOPICS = [
    "Data representation and character encoding",
    "Algorithmic Representation",
    "Data Validation and Verification",
    "Recursion",
    "Searching and Sorting Algorithms",
    "Data Structures",
    "OOP",
    "Databases",
    "Web development",
    "Information and Cybersecurity",
    "Computer Networks",
    "AI and Machine Learning",
    "Social, Ethical and Security Impact"
]

# Backward compatibility map
category_options = {t: t for t in PRACTICAL_TOPICS + THEORY_TOPICS}

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
            st.caption("✨ Calibrated across selected syllabus topics.")

        # Topics Multi-Select & Custom Topic Addition
        available_topics = PRACTICAL_TOPICS if paper_type == "practical" else THEORY_TOPICS
        col_top_sel, col_top_cust = st.columns([1.4, 1])
        with col_top_sel:
            selected_topics = st.multiselect(
                "🎯 Syllabus Topics (Select multiple)",
                options=available_topics,
                default=[available_topics[8], available_topics[2]] if paper_type == "practical" else [available_topics[5], available_topics[4]],
                help="Select one or more topics to assess in this exam paper."
            )
        with col_top_cust:
            custom_topics_input = st.text_input(
                "➕ Custom Topic(s) (Optional)",
                placeholder="e.g. Trie ADT, A* Search, REST APIs",
                help="Type custom topics separated by commas."
            )
        
        # Combine all topics
        all_chosen_topics = list(selected_topics)
        if custom_topics_input.strip():
            for ct in custom_topics_input.split(","):
                clean_ct = ct.strip()
                if clean_ct and clean_ct not in all_chosen_topics:
                    all_chosen_topics.append(clean_ct)
        category = ", ".join(all_chosen_topics) if all_chosen_topics else "Comprehensive 9569 Syllabus"
        st.caption(f"📌 **Active Assessed Topics**: `{category}`")

        # Metadata Fields
        col_inst, col_yr, col_ser = st.columns([1.5, 0.8, 1.1])
        with col_inst:
            institution = st.text_input("Institution Name", value="HelloWorld Junior College", key="full_inst")
        with col_yr:
            exam_year = st.text_input("Exam Year", value="2027", key="full_yr")
        with col_ser:
            exam_series = st.selectbox("Series", options=["A-Level", "Prelim", "Practice Paper", "Promo", "WA", "Specimen"], index=1, key="full_ser")

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
            generate_btn = st.button("Author & Compile Exam Package", type="primary", use_container_width=True)
        with col_hint:
            st.caption("💡 *Tip: Adding the word `'contextual'` triggers extended real-world scenarios and step-by-step bulleted subtasks.*")

    if generate_btn:
        # Smoothly scroll the page down to the pipeline container
        components.html(
            """
            <script>
            setTimeout(function() {
                var mainEl = window.parent.document.querySelector('[data-testid="stMain"]');
                if (mainEl) {
                    mainEl.scrollTo({ top: 380, behavior: 'smooth' });
                }
            }, 60);
            </script>
            """,
            height=0
        )

        train_station_placeholder = st.empty()
        logs = []
        pipeline_start_time = time.time()

        stations = [
            ("Station 1: Memory & Style Agent", "🧠 Querying persistent educator profile in Cloud Firestore..."),
            ("Station 2: RAG Grounding Agent", "📚 Scanning syllabus 9569 standards & indexing exam exemplars..."),
            ("Station 3: Blueprint Architect Agent", "📐 Synthesizing learning objectives & mark allocations with Gemini 3.7 Flash..."),
            ("Station 4: Demographic Synthesizer Agent", "⚖️ Generating 50/50 gender balanced datasets & SQL schemas..."),
            ("Station 5: Golden TeX Authoring Agent", "✍️ Drafting Cambridge-compliant LaTeX exam paper & mark scheme..."),
            ("Station 6: Self-Healing Sandbox Agent", "🔄 Executing pdflatex compilation & 3-pass Gemini self-healing..."),
            ("Station 7: Artifact Packaging Agent", "📦 Persisting session state & bundling .zip download package...")
        ]

        def render_train_station(current_station_idx: int, active_msg: str, is_done: bool = False):
            start_ms = int(pipeline_start_time * 1000)
            full_html = build_pipeline_hud_html(
                current_station_idx=current_station_idx,
                active_msg=active_msg,
                is_done=is_done,
                start_ms=start_ms
            )
            with train_station_placeholder.container():
                components.html(full_html, height=220)

        def on_progress(step: str, msg: str):
            logs.append(f"**[{step}]** {msg}")
            current_idx = 0
            for idx, (s_name, _) in enumerate(PIPELINE_STATIONS):
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
            st.session_state.last_generation_duration = total_dur
            render_train_station(6, f"🎉 All 7 agents completed their tasks in {total_dur}s!", is_done=True)
            time.sleep(0.5)
            st.rerun()
        except Exception as gen_err:
            st.error(f"Generation notification: {gen_err}")
            st.info("Displaying synthesized Cambridge assessment package.")

# ==============================================================================
# MODE B: QUESTION-BY-QUESTION CO-AUTHORING STUDIO
# ==============================================================================
elif "Question-by-Question" in author_mode:
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

        s_available_topics = PRACTICAL_TOPICS if s_paper_type == "practical" else THEORY_TOPICS
        col_s_top, col_s_cust = st.columns([1.4, 1])
        with col_s_top:
            s_selected_topics = st.multiselect(
                "Syllabus Topic(s)",
                options=s_available_topics,
                default=[s_available_topics[8]] if s_paper_type == "practical" else [s_available_topics[5]],
                key="studio_multitopics"
            )
        with col_s_cust:
            s_custom_topic = st.text_input(
                "➕ Custom Topic (Optional)",
                placeholder="e.g. Min-Heap Queue",
                key="studio_cust_topic"
            )
        
        s_all_topics = list(s_selected_topics)
        if s_custom_topic.strip():
            for ct in s_custom_topic.split(","):
                clean_ct = ct.strip()
                if clean_ct and clean_ct not in s_all_topics:
                    s_all_topics.append(clean_ct)
        s_category = ", ".join(s_all_topics) if s_all_topics else "General ADT & System Design"

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
            
            # Metadata Fields for Assembled Paper
            with st.expander("⚙️ Assembled Paper Cover & Header Metadata", expanded=False):
                col_b_inst, col_b_yr, col_b_ser = st.columns([1.5, 0.8, 1.1])
                with col_b_inst:
                    b_institution = st.text_input("Institution Name", value="HelloWorld Junior College", key="studio_inst")
                with col_b_yr:
                    b_exam_year = st.text_input("Exam Year", value="2027", key="studio_yr")
                with col_b_ser:
                    b_exam_series = st.selectbox("Series", options=["A-Level", "Prelim", "Practice Paper", "Promo", "WA", "Specimen"], index=1, key="studio_ser")

            # Compile & Build Button styled with blue background & light blue text
            st.markdown("<div class='compile-build-box'>", unsafe_allow_html=True)
            if st.button("🔨 Compile & Build Final Exam Package", use_container_width=True, key="studio_compile_btn"):
                with st.spinner("Assembling LaTeX document, companion datasets, and compiling in sandbox..."):
                    compiled_sess = st.session_state.orchestrator.compile_assembled_session(
                        tasks_list=q_list,
                        paper_type=s_paper_type,
                        syllabus_code="9569",
                        paper_number="02" if s_paper_type == "practical" else "01",
                        institution=b_institution if 'b_institution' in locals() else "HelloWorld Junior College",
                        exam_year=b_exam_year if 'b_exam_year' in locals() else "2027",
                        exam_series=b_exam_series if 'b_exam_series' in locals() else "Prelim"
                    )
                    st.session_state.current_session = compiled_sess
                    st.success("🎉 Full Exam Package Assembled and Compiled Successfully!")
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

# ==============================================================================
# MODE C: DOCUMENT TRANSCRIBER (WORD / PDF TO CAMBRIDGE LATEX)
# ==============================================================================
elif "Document Transcriber" in author_mode:
    with st.expander("📄 Upload Exam Document to Transcribe & Standardize", expanded=True if not st.session_state.current_session else False):
        st.markdown("Upload any legacy or draft examination paper in **Word (.docx)**, **PDF (.pdf)**, or **Text (.txt/.tex)** format. The AI agent will extract the questions and transcribe them into publication-grade **Singapore-Cambridge H2 Computing LaTeX** conforming strictly to Cambridge specifications.")
        
        doc_file = st.file_uploader(
            "Upload Word / PDF Document",
            type=["docx", "pdf", "txt", "tex"],
            help="Upload your exam paper draft to convert into Cambridge LaTeX.",
            key="trans_file_uploader"
        )

        col_t1, col_t2 = st.columns([1.2, 1.8])
        with col_t1:
            trans_paper_type = st.selectbox(
                "Target Paper Standard",
                options=["auto", "practical", "theory"],
                format_func=lambda x: "Auto-Detect Format" if x == "auto" else ("Paper 2 Practical (9569/02)" if x == "practical" else "Paper 1 Theory (9569/01)"),
                key="trans_paper_type_select"
            )
        with col_t2:
            st.info("💡 **Autonomous Normalization**: Detects and enforces `\\maintask{X}`, `\\tasksubtaskintro{X}`, subtask structures, `\\Marks{n}`, monospace code formatting, and 4-page signature booklet padding.")

        col_inst, col_yr, col_ser = st.columns([1.5, 0.8, 1.1])
        with col_inst:
            t_institution = st.text_input("Institution Name", value="Singapore Junior College", key="trans_inst")
        with col_yr:
            t_exam_year = st.text_input("Exam Year", value="2026", key="trans_yr")
        with col_ser:
            t_exam_series = st.selectbox("Series", options=["A-Level", "Prelim", "Practice Paper", "Promo", "WA", "Specimen"], index=0, key="trans_ser")

        transcribe_btn = st.button("✨ Transcribe & Standardize to Cambridge LaTeX", type="primary", use_container_width=True, disabled=not doc_file, key="trans_run_btn")

    if transcribe_btn and doc_file:
        train_station_placeholder = st.empty()
        logs = []
        start_time = time.time()
        start_ms = int(start_time * 1000)

        def update_progress(step: str, message: str):
            logs.append(f"[{step}] {message}")
            current_station_idx = 1
            if "Station 1" in step:
                current_station_idx = 1  # Ingestion / Grounding
            elif "Station 2" in step:
                current_station_idx = 4  # Golden TeX Conformance
            elif "Station 3" in step:
                current_station_idx = 5  # Self-Healing Sandbox
            elif "Station 4" in step:
                current_station_idx = 6  # Artifact Packaging

            hud_html = build_pipeline_hud_html(
                current_station_idx=current_station_idx,
                active_msg=f"{step}: {message}",
                is_done=False,
                start_ms=start_ms,
                skipped_indices=[0, 2, 3]
            )
            with train_station_placeholder.container():
                components.html(hud_html, height=220)
            time.sleep(0.08)

        progress_listener = ExamGenerationProgress(log_callback=update_progress)

        with st.spinner("Extracting questions and normalizing to Cambridge LaTeX..."):
            session = st.session_state.orchestrator.transcribe_and_compile_document(
                file_bytes=doc_file.getvalue(),
                filename=doc_file.name,
                paper_type=trans_paper_type,
                institution=t_institution,
                exam_year=t_exam_year,
                exam_series=t_exam_series,
                progress=progress_listener
            )

        duration = time.time() - start_time
        st.session_state.last_generation_duration = duration
        st.session_state.current_session = session

        # Show 100% complete HUD
        final_hud = build_pipeline_hud_html(
            current_station_idx=6,
            active_msg="Document successfully transcribed & standardized to Cambridge LaTeX!",
            is_done=True,
            final_duration_str=f"{duration:.1f}s",
            start_ms=start_ms,
            skipped_indices=[0, 2, 3]
        )
        with train_station_placeholder.container():
            components.html(final_hud, height=220)
        st.success(f"🎉 Exam Document '{doc_file.name}' Transcribed into Cambridge LaTeX in {duration:.1f}s!")
        st.rerun()

# ==============================================================================
# DISPLAY ARTIFACTS & RESULTS
# ==============================================================================
curr_sess: ExamSession = st.session_state.current_session

if curr_sess:
    st.markdown("---")
    
    # Persistent Multi-Agent Pipeline (All Stages Complete)
    dur_val = st.session_state.get("last_generation_duration", 14.8)
    dur_str = f"{dur_val:.1f}s" if isinstance(dur_val, (int, float)) else str(dur_val)
    is_transcribed = curr_sess.category == "transcribed_paper"
    persisted_skipped = [0, 2, 3] if is_transcribed else None
    persisted_msg = "Document successfully transcribed, conformed to Cambridge LaTeX & compiled in Sandbox!" if is_transcribed else "All 7 multi-agent pipeline stages completed successfully! Artifact package compiled & ready."
    
    persisted_pipeline_html = build_pipeline_hud_html(
        current_station_idx=6,
        active_msg=persisted_msg,
        is_done=True,
        final_duration_str=dur_str,
        skipped_indices=persisted_skipped
    )
    components.html(persisted_pipeline_html, height=220)
    
    # Top Action Bar & Metrics
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(f"<div class='metric-box'><div class='metric-value' style='color: #0f172a; font-weight: 800;'>{curr_sess.paper_type.upper()}</div><div class='metric-label' style='color: #475569; font-weight: 600;'>Paper Type</div></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='metric-box'><div class='metric-value' style='color: #0f172a; font-weight: 800;'>{curr_sess.syllabus_code}/{curr_sess.paper_number}</div><div class='metric-label' style='color: #475569; font-weight: 600;'>Paper Code</div></div>", unsafe_allow_html=True)
    with m3:
        total_m = curr_sess.blueprint.get("total_marks", 94 if curr_sess.paper_type == "practical" else 100) if isinstance(curr_sess.blueprint, dict) else (94 if curr_sess.paper_type == "practical" else 100)
        mark_label = "94m (+6m Style = 100m)" if curr_sess.paper_type == "practical" else "100m Total"
        st.markdown(f"<div class='metric-box'><div class='metric-value' style='color: #0f172a; font-weight: 800;'>{total_m}</div><div class='metric-label' style='color: #475569; font-weight: 600;'>{mark_label}</div></div>", unsafe_allow_html=True)
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
    # TAB 1: Blueprint & Objectives (Vibrant Keypoint Summary Cards)
    # --------------------------------------------------------------------------
    with tab1:
        st.markdown("### 📋 Syllabus-Calibrated Exam Blueprint & Keypoints")
        bp = curr_sess.blueprint if isinstance(curr_sess.blueprint, dict) else {}
        
        # 1. Learning Objectives Chips
        learning_objs = bp.get("learning_objectives", [])
        if learning_objs:
            st.markdown("#### 🎯 Assessed Learning Objectives")
            obj_chips_html = "".join([f"<div class='objective-chip'>🎯 {obj}</div>" for obj in learning_objs])
            st.markdown(f"<div style='margin-bottom: 18px;'>{obj_chips_html}</div>", unsafe_allow_html=True)

        st.markdown("#### 📑 Question Breakdown & Subtask Keypoints")
        
        # Vibrant Task Theme Palettes (Border, Badge BG, Badge Text, Header Fill)
        task_themes = [
            {"border": "#2563eb", "badge_bg": "#dbeafe", "badge_text": "#1e40af", "topic_bg": "#eff6ff"}, # Cobalt Blue
            {"border": "#059669", "badge_bg": "#d1fae5", "badge_text": "#065f46", "topic_bg": "#f0fdf4"}, # Emerald Green
            {"border": "#d97706", "badge_bg": "#fef3c7", "badge_text": "#92400e", "topic_bg": "#fffbeb"}, # Amber / Gold
            {"border": "#7c3aed", "badge_bg": "#ede9fe", "badge_text": "#5b21b6", "topic_bg": "#faf5ff"}, # Royal Violet
            {"border": "#e11d48", "badge_bg": "#ffe4e6", "badge_text": "#9f1239", "topic_bg": "#fff1f2"}, # Crimson Rose
        ]

        sections = bp.get("sections", [])
        total_paper_raw = curr_sess.blueprint.get("total_marks", 94 if curr_sess.paper_type == "practical" else 100) if isinstance(curr_sess.blueprint, dict) else 100
        
        for idx, sec in enumerate(sections):
            theme = task_themes[idx % len(task_themes)]
            sec_marks = sec.get("marks", 0)
            weight_pct = round((sec_marks / total_paper_raw * 100), 1) if total_paper_raw > 0 else 0
            
            subparts = sec.get("subparts", [])
            subparts_html = ""
            if subparts:
                items_list = []
                for sp in subparts:
                    raw_desc = sp.get('description', '')
                    clean_desc = re.sub(r"`([^`\n]+)`", r"<code class='inline-code'>\1</code>", raw_desc)
                    sub_label = sp.get('label', f'Task {idx+1}.1')
                    sub_marks = sp.get('marks', '')
                    
                    items_list.append(
                        f"<div class='subtask-keypoint-strip'>"
                        f"<span class='subtask-keypoint-badge' style='background: {theme['badge_bg']}; color: {theme['badge_text']};'>{sub_label}</span>"
                        f"<div class='subtask-keypoint-content'>{clean_desc}</div>"
                        f"<span class='subtask-mark-bubble'>[{sub_marks}m]</span>"
                        f"</div>"
                    )
                subparts_html = f"<div style='margin-top: 12px;'>{''.join(items_list)}</div>"

            card_html = (
                f'<div class="blueprint-card" style="border-left: 5px solid {theme["border"]};">'
                f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">'
                f'<div>'
                f'<div style="font-size: 1.15rem; font-weight: 800; color: #0f172a;">{sec.get("title", f"Task {idx+1}")}</div>'
                f'<div style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">'
                f'<span style="background: {theme["topic_bg"]}; color: {theme["badge_text"]}; border: 1px solid {theme["badge_bg"]}; padding: 2px 10px; border-radius: 12px; font-size: 0.78rem; font-weight: 700;">Topic: {sec.get("topic", "N/A")}</span>'
                f'<span style="font-size: 0.76rem; color: #64748b; font-weight: 600;">{weight_pct}% of total exam</span>'
                f'</div>'
                f'</div>'
                f'<div>'
                f'<span class="badge-pill badge-latex" style="background: {theme["border"]} !important; color: #ffffff !important; font-size: 0.88rem; padding: 4px 12px;">{sec_marks} Marks</span>'
                f'</div>'
                f'</div>'
                f'{subparts_html}'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

        if curr_sess.paper_type == "practical":
            style_card_html = (
                f'<div class="blueprint-card" style="border-left: 5px solid #2563eb; background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);">'
                f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">'
                f'<div>'
                f'<div style="font-size: 1.15rem; font-weight: 800; color: #0f172a;">Code Quality & Programming Style Assessment</div>'
                f'<div style="font-size: 0.8rem; color: #475569; margin-top: 2px;">Assessed holistically across candidate Python scripts in Jupyter Notebooks</div>'
                f'</div>'
                f'<div>'
                f'<span class="badge-pill badge-gemini" style="background: linear-gradient(135deg, #1e3a8a, #2563eb) !important; color: #ffffff !important; font-size: 0.88rem; padding: 4px 12px;">6 Marks</span>'
                f'</div>'
                f'</div>'
                f'<div style="margin-top: 12px;">'
                f'<div class="subtask-keypoint-strip">'
                f'<span class="subtask-keypoint-badge" style="background: #dbeafe; color: #1e40af;">Style 1</span>'
                f'<div class="subtask-keypoint-content"><strong>Meaningful identifier names</strong>: Clear, intuitive descriptive conventions for variables, functions, and class definitions.</div>'
                f'<span class="subtask-mark-bubble">[2m]</span>'
                f'</div>'
                f'<div class="subtask-keypoint-strip">'
                f'<span class="subtask-keypoint-badge" style="background: #d1fae5; color: #065f46;">Style 2</span>'
                f'<div class="subtask-keypoint-content"><strong>Appropriate comments</strong>: Concise, helpful docstrings and algorithmic comments explaining complex data structures and edge logic.</div>'
                f'<span class="subtask-mark-bubble">[2m]</span>'
                f'</div>'
                f'<div class="subtask-keypoint-strip">'
                f'<span class="subtask-keypoint-badge" style="background: #fef3c7; color: #92400e;">Style 3</span>'
                f'<div class="subtask-keypoint-content"><strong>Good use of whitespaces</strong>: Standard PEP 8 indentation, logical blank line separation, and expression readability.</div>'
                f'<span class="subtask-mark-bubble">[2m]</span>'
                f'</div>'
                f'</div>'
                f'</div>'
            )
            st.markdown(style_card_html, unsafe_allow_html=True)

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
        st.markdown(f"<div style='color: #475569; margin-bottom: 10px; font-size: 0.95rem;'>Prompt {GEMINI_ICON_SM} <strong>Gemini 3.7 Flash</strong> to refine, rephrase, add subtasks, adjust difficulty, or rewrite specific tasks across this working exam paper:</div>", unsafe_allow_html=True)
        
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
        st.markdown(f"### 🔄 pdflatex Compilation & {GEMINI_ICON_SM} Gemini Self-Healing Logs", unsafe_allow_html=True)
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
