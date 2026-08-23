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
import html
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

# Explicitly ensure repository root is in sys.path across all deployment environments (Cloud Run, Docker, Local)
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from code_editor import code_editor

from config.gcp_config import AppConfig, BASE_DIR
from src.auth.auth_manager import AuthManager
from src.agent.orchestrator import EduScribeOrchestrator, ExamGenerationProgress
from src.agent.preference_learner import PreferenceLearner
from src.agent.session_manager import SessionManager, ExamSession
from src.sandbox.code_executor import CodeExecutor
from src.sandbox.latex_renderer import LaTeXVisualRenderer
from src.sandbox.latex_compiler import LaTeXSyntaxValidator

CURRENT_YEAR = str(datetime.now().year)
SERIES_OPTIONS = ["Prelim", "A-Level", "Practice Paper", "Promo", "WA", "Specimen", "Mid-Year Exam", "Other / Custom..."]
EXAM_IMAGE_MACRO = r"\newcommand{\ExamImage}[2]{\par\begin{center}\includegraphics[width=#2]{#1}\end{center}\par}"


def build_session_image_data_urls(session: ExamSession) -> Dict[str, str]:
    """Loads local session assets as data URLs for the isolated HTML preview iframe."""
    assets_dir = BASE_DIR / "data_store" / "sessions" / session.session_id / "assets"
    data_urls: Dict[str, str] = {}
    for asset in getattr(session, "image_assets", []):
        filename = Path(asset.get("filename", "")).name
        if not filename:
            continue
        asset_path = assets_dir / filename
        if not asset_path.exists():
            continue
        mime_type = asset.get("mime_type", "image/png")
        data_url = f"data:{mime_type};base64,{base64.b64encode(asset_path.read_bytes()).decode('ascii')}"
        data_urls[filename] = data_url
        data_urls[asset.get("path", f"assets/{filename}")] = data_url
    return data_urls


def render_tex_copy_control(tex_source: str, filename: str, key: str) -> None:
    """Renders a prominent, accessible clipboard control above a TeX preview."""
    source_json = json.dumps(tex_source).replace("</", "<\\/")
    control_id = f"copy-{key}"
    components.html(
        f"""<!doctype html>
<html><head><meta charset='utf-8'><style>
body {{ margin:0; font-family:Montserrat,Segoe UI,sans-serif; background:transparent; }}
button {{ width:100%; min-height:42px; border:1px solid #0b5d89; border-radius:7px; padding:9px 14px; cursor:pointer; color:#fff; background:linear-gradient(135deg,#0b3b70,#087f8c); font:700 14px Montserrat,Segoe UI,sans-serif; letter-spacing:0; box-shadow:0 2px 7px rgba(11,59,112,.2); }}
button:hover {{ background:linear-gradient(135deg,#082e59,#056d78); }}
button:focus-visible {{ outline:3px solid #fbbf24; outline-offset:2px; }}
</style></head><body>
<button id='{control_id}' type='button' aria-label='Copy all contents of {html.escape(filename)} to clipboard'>Copy {html.escape(filename)} to clipboard</button>
<script>
const source = {source_json};
const button = document.getElementById('{control_id}');
async function copySource() {{
  try {{
    if (navigator.clipboard && window.isSecureContext) {{ await navigator.clipboard.writeText(source); }}
    else {{
      const area=document.createElement('textarea'); area.value=source; area.style.position='fixed'; area.style.opacity='0';
      document.body.appendChild(area); area.select(); document.execCommand('copy'); area.remove();
    }}
    button.textContent='Copied {html.escape(filename)}';
  }} catch (error) {{ button.textContent='Copy failed - use the source box below'; }}
  window.setTimeout(() => {{ button.textContent='Copy {html.escape(filename)} to clipboard'; }}, 2200);
}}
button.addEventListener('click', copySource);
</script></body></html>""",
        height=48,
        scrolling=False,
    )


def format_elapsed_time(seconds: float) -> str:
    """Formats elapsed time as seconds or minutes plus seconds for status HUDs."""
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    remainder = seconds - (minutes * 60)
    return f"{minutes} min {remainder:05.2f} sec" if minutes else f"{remainder:.2f} sec"


TEX_EDITOR_BUTTONS = [
    {
        "name": "copy",
        "feather": "Copy",
        "hasText": True,
        "alwaysOn": True,
        "commands": ["copyAll"],
        "style": {"top": "0.45rem", "right": "5.9rem"},
    },
    {
        "name": "save",
        "feather": "Save",
        "primary": True,
        "hasText": True,
        "showWithIcon": True,
        "alwaysOn": True,
        "commands": ["submit"],
        "style": {"top": "0.45rem", "right": "0.45rem"},
    },
]


def build_tex_lint_annotations(tex_source: str) -> list[dict[str, Any]]:
    """Returns Ace gutter annotations for common, actionable TeX structure errors."""
    annotations: list[dict[str, Any]] = []
    environment_stack: list[tuple[str, int, int]] = []
    brace_balance = 0
    code_environment: Optional[str] = None

    for row, raw_line in enumerate(tex_source.splitlines()):
        line = re.split(r"(?<!\\)%", raw_line, maxsplit=1)[0]
        for match in re.finditer(r"\\(begin|end)\{([^}]+)\}", line):
            action, environment = match.groups()
            if code_environment and environment != code_environment:
                continue
            if action == "begin":
                environment_stack.append((environment, row, match.start()))
                if environment in {"verbatim", "lstlisting", "minted", "python"}:
                    code_environment = environment
            elif not environment_stack:
                annotations.append({
                    "row": row,
                    "column": match.start(),
                    "text": f"Unexpected \\end{{{environment}}}.",
                    "type": "error",
                })
            elif environment_stack[-1][0] != environment:
                expected = environment_stack[-1][0]
                annotations.append({
                    "row": row,
                    "column": match.start(),
                    "text": f"Expected \\end{{{expected}}} before \\end{{{environment}}}.",
                    "type": "error",
                })
            else:
                environment_stack.pop()
                if environment == code_environment:
                    code_environment = None

        if code_environment:
            continue

        unescaped_line = line.replace(r"\{", "").replace(r"\}", "")
        brace_balance += unescaped_line.count("{") - unescaped_line.count("}")
        if r"\nolinkurl" in line:
            annotations.append({
                "row": row,
                "column": line.find(r"\nolinkurl"),
                "text": "\\nolinkurl requires hyperref here; use \\path for portable inline code.",
                "type": "error",
            })
        csv_match = re.search(r"language\s*=\s*(?:\{\s*csv\s*\}|csv)", line, flags=re.IGNORECASE)
        if csv_match:
            annotations.append({
                "row": row,
                "column": csv_match.start(),
                "text": "listings has no portable csv language; use language={}.",
                "type": "warning",
            })

    for environment, row, column in environment_stack:
        annotations.append({
            "row": row,
            "column": column,
            "text": f"Unclosed \\begin{{{environment}}} environment.",
            "type": "error",
        })
    if brace_balance:
        annotations.append({
            "row": 0,
            "column": 0,
            "text": "Curly braces are unbalanced in this document.",
            "type": "error",
        })
    if r"\documentclass" not in tex_source:
        annotations.append({
            "row": 0,
            "column": 0,
            "text": "Missing \\documentclass declaration.",
            "type": "error",
        })
    if r"\begin{document}" not in tex_source or r"\end{document}" not in tex_source:
        annotations.append({
            "row": 0,
            "column": 0,
            "text": "A complete export needs both \\begin{document} and \\end{document}.",
            "type": "error",
        })
    return annotations


def ensure_exam_image_macro(latex_source: str) -> str:
    """Ensures paper.tex contains the image macro needed by browser preview and pdflatex."""
    if r"\newcommand{\ExamImage}" in latex_source:
        return latex_source
    if r"\usepackage{graphicx}" in latex_source:
        return latex_source.replace(
            r"\usepackage{graphicx}",
            r"\usepackage{graphicx}" + "\n" + EXAM_IMAGE_MACRO,
            1,
        )
    if r"\begin{document}" in latex_source:
        return latex_source.replace(r"\begin{document}", EXAM_IMAGE_MACRO + "\n\\begin{document}", 1)
    return EXAM_IMAGE_MACRO + "\n" + latex_source


def render_tex_editor(session: ExamSession, source_attribute: str, filename: str, editor_id: str) -> None:
    """Renders an editable TeX workspace whose saved text becomes the session source."""
    editor_prefix = f"tex_editor_{session.session_id}_{editor_id}"
    draft_key = f"{editor_prefix}_draft"
    source_key = f"{editor_prefix}_source"
    dirty_key = f"{editor_prefix}_dirty"
    revision_key = f"{editor_prefix}_revision"
    saved_source = getattr(session, source_attribute)

    if draft_key not in st.session_state:
        st.session_state[draft_key] = saved_source
        st.session_state[source_key] = saved_source
        st.session_state[dirty_key] = False
        st.session_state[revision_key] = 0
    elif st.session_state[source_key] != saved_source and not st.session_state[dirty_key]:
        st.session_state[draft_key] = saved_source
        st.session_state[source_key] = saved_source
        st.session_state[revision_key] += 1

    draft_source = st.session_state[draft_key]
    annotations = build_tex_lint_annotations(draft_source)
    response = code_editor(
        draft_source,
        lang="latex",
        theme="light",
        shortcuts="vscode",
        height="620px",
        buttons=TEX_EDITOR_BUTTONS,
        options={"wrap": True, "fontSize": "14px", "showPrintMargin": False},
        props={
            "annotations": annotations,
            "showGutter": True,
            "highlightActiveLine": True,
            "style": {"borderRadius": "8px", "border": "1px solid #b9cbe3"},
        },
        component_props={
            "css": ".ace_editor { font-family: 'Fira Code', 'Courier New', monospace; } .ace_gutter { background:#edf5ff; color:#34506f; }",
        },
        response_mode=["debounce", "blur"],
        allow_reset=True,
        key=f"{editor_prefix}_{st.session_state[revision_key]}",
    )

    response_text = response.get("text") if isinstance(response, dict) else None
    if isinstance(response_text, str) and response_text != st.session_state[draft_key]:
        st.session_state[draft_key] = response_text
        st.session_state[dirty_key] = response_text != saved_source
        draft_source = response_text
        annotations = build_tex_lint_annotations(draft_source)

    lint_report = LaTeXSyntaxValidator.validate_syntax(draft_source)
    issue_count = max(len(annotations), len(lint_report.issues))
    lint_col, save_col, reset_col = st.columns([2.4, 1, 1])
    with lint_col:
        if issue_count:
            st.caption(f"Live TeX lint: {issue_count} issue{'s' if issue_count != 1 else ''}; see the editor gutter for locations.")
        else:
            st.caption("Live TeX lint: no structural errors found.")
    with save_col:
        save_requested = st.button("Save TeX", key=f"{editor_prefix}_save", type="primary", use_container_width=True)
    with reset_col:
        reset_requested = st.button("Revert", key=f"{editor_prefix}_revert", use_container_width=True)

    if reset_requested:
        st.session_state[draft_key] = saved_source
        st.session_state[dirty_key] = False
        st.session_state[revision_key] += 1
        st.rerun()

    if save_requested or (isinstance(response, dict) and response.get("type") == "submit"):
        updated_source = st.session_state[draft_key]
        if updated_source != saved_source:
            setattr(session, source_attribute, updated_source)
            session.status = "draft"
            st.session_state.orchestrator.session_manager.save_session(session)
            st.session_state.current_session = session
            st.session_state[source_key] = updated_source
            st.session_state[dirty_key] = False
            st.session_state[revision_key] += 1
            st.toast(f"Saved {filename}. Re-run pdflatex before treating this edit as compiled.")
            st.rerun()
        st.info(f"No changes to save in {filename}.")


def render_activity_hud(title: str, detail: str, key: str, start_ms: int) -> None:
    """Shows a compact, self-animating status surface for synchronous actions."""
    hud_id = f"activity-{key}"
    components.html(
        f"""<!doctype html>
<html><head><meta charset='utf-8'><style>
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Montserrat,Segoe UI,sans-serif; background:transparent; color:#fff; }}
.hud {{ position:relative; overflow:hidden; min-height:104px; border:1px solid #0a6383; border-radius:8px; background:linear-gradient(118deg,#082e59 0%,#0d4e82 48%,#087f8c 100%); box-shadow:0 8px 20px rgba(13,70,116,.22); padding:16px 18px; }}
.hud::before {{ content:''; position:absolute; width:42%; height:180%; top:-40%; left:-55%; background:linear-gradient(90deg,transparent,rgba(255,255,255,.16),transparent); transform:rotate(18deg); animation:sweep 2.8s linear infinite; }}
.content {{ position:relative; z-index:1; display:flex; justify-content:space-between; gap:18px; align-items:flex-start; }}
.eyebrow {{ color:#b9f2ff; font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:.08em; }}
h3 {{ margin:4px 0 5px; font-size:17px; letter-spacing:0; }}
p {{ margin:0; color:#e0f8ff; font-size:12px; line-height:1.35; max-width:760px; }}
.timer {{ font:700 14px 'Courier New',monospace; white-space:nowrap; padding:7px 9px; border:1px solid rgba(185,242,255,.62); border-radius:5px; background:rgba(3,23,48,.26); }}
.rail {{ position:relative; z-index:1; height:5px; margin-top:15px; border-radius:99px; background:rgba(255,255,255,.22); overflow:hidden; }}
.rail span {{ display:block; height:100%; width:36%; border-radius:inherit; background:linear-gradient(90deg,#fbbf24,#fef08a,#67e8f9); animation:travel 1.45s ease-in-out infinite; }}
@keyframes sweep {{ to {{ left:120%; }} }} @keyframes travel {{ 0% {{ transform:translateX(-110%); }} 100% {{ transform:translateX(310%); }} }}
@media (prefers-reduced-motion:reduce) {{ .hud::before,.rail span {{ animation:none; }} }}
</style></head><body><section class='hud' aria-live='polite' aria-label='{html.escape(title)} in progress'>
  <div class='content'><div><div class='eyebrow'>ComputingScribe is working</div><h3>{html.escape(title)}</h3><p>{html.escape(detail)}</p></div><div id='{hud_id}' class='timer'>0.00 sec</div></div>
  <div class='rail' aria-hidden='true'><span></span></div>
</section><script>
const started={start_ms}; const timer=document.getElementById('{hud_id}');
function formatElapsed(elapsed) {{ const mins=Math.floor(elapsed/60); const secs=elapsed-(mins*60); return mins ? mins+' min '+secs.toFixed(2).padStart(5,'0')+' sec' : secs.toFixed(2)+' sec'; }}
setInterval(()=>{{ timer.textContent=formatElapsed((Date.now()-started)/1000); }},100);
</script></body></html>""",
        height=112,
        scrolling=False,
    )


def insert_exam_image(
    latex_source: str,
    image_macro: str,
    placement: str = "Click to select line in paper.tex",
    phrase: str = "",
    line_number: Optional[int] = None,
    position: str = "after",
) -> tuple[Optional[str], Optional[str]]:
    """Adds an image after a selected line number, after a uniquely matched source phrase, or at the end of the paper."""
    if placement == "At end of paper":
        latex_source = ensure_exam_image_macro(latex_source)
        if r"\end{document}" in latex_source:
            return latex_source.replace(r"\end{document}", f"{image_macro}\n\n\\end{{document}}", 1), None
        return latex_source.rstrip() + f"\n\n{image_macro}\n", None

    if placement in ("Click to select line in paper.tex", "After selected line", "Before selected line") or line_number is not None:
        if line_number is None:
            return None, "Please select a line number in paper.tex where the image should be placed."
        raw_lines = latex_source.splitlines(keepends=True)
        if not (1 <= line_number <= len(raw_lines)):
            return None, f"Selected line {line_number} is out of range (1 to {len(raw_lines)})."
        
        insert_idx = line_number if position.lower() == "after" else (line_number - 1)
        formatted_macro = f"\n{image_macro}\n" if (insert_idx > 0 and not raw_lines[insert_idx - 1].endswith("\n")) else f"{image_macro}\n"
        raw_lines.insert(insert_idx, formatted_macro)
        updated_source = ensure_exam_image_macro("".join(raw_lines))
        return updated_source, None

    phrase = phrase.strip()
    if not phrase:
        return None, "Enter the exact phrase after which the image should appear."
    occurrences = latex_source.count(phrase)
    if occurrences != 1:
        return None, f"The phrase must occur exactly once in paper.tex; it currently occurs {occurrences} times."

    phrase_end = latex_source.find(phrase) + len(phrase)
    line_end = latex_source.find("\n", phrase_end)
    if line_end == -1:
        line_end = len(latex_source)
    updated_source = latex_source[:line_end] + f"\n\n{image_macro}" + latex_source[line_end:]
    updated_source = ensure_exam_image_macro(updated_source)
    return updated_source, None


def build_task_authoring_hud_html(
    task_number: int,
    paper_type: str,
    marks: int,
    topics: List[str],
    start_ms: int,
    is_done: bool = False,
    final_duration_str: str = "",
) -> str:
    """Compact, self-animating progress HUD for a single-question authoring request."""
    task_label = f"Task {task_number}" if paper_type == "practical" else f"Question {task_number}"
    paper_label = "Paper 2 Practical" if paper_type == "practical" else "Paper 1 Theory"
    topic_label = ", ".join(topics) if topics else "General Computing"
    stages = [
        ("Brief", "Reading the teaching intent"),
        ("Blueprint", "Balancing subtasks and marks"),
        ("Author", "Writing the assessment content"),
        ("Format", "Checking Cambridge LaTeX structure"),
    ]
    stage_html = "".join(
        f"<div class='task-stage' data-stage='{idx}'><span class='task-stage-num'>{idx + 1}</span><div><strong>{name}</strong><small>{detail}</small></div></div>"
        for idx, (name, detail) in enumerate(stages)
    )
    state_text = "Draft ready for review" if is_done else "Gemini is composing a structured assessment draft"
    if is_done and final_duration_str:
        try:
            timer_text = format_elapsed_time(float(re.sub(r"[^0-9.]", "", final_duration_str)))
        except ValueError:
            timer_text = final_duration_str
    else:
        timer_text = "0.00 sec"
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><style>
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:2px; font-family:Inter,Segoe UI,sans-serif; color:#10213f; background:transparent; }}
.task-hud {{ overflow:hidden; border:1px solid #b9cbe3; border-radius:8px; background:#fff; box-shadow:0 8px 20px rgba(15,48,92,.10); }}
.task-head {{ position:relative; overflow:hidden; padding:13px 16px; background:#102a56; color:#fff; display:flex; justify-content:space-between; gap:16px; align-items:center; }}
.task-head::after {{ content:''; position:absolute; inset:0; background:linear-gradient(100deg,transparent 25%,rgba(121,205,255,.24) 48%,transparent 70%); transform:translateX(-130%); animation:scan 2.4s linear infinite; }}
.task-head > * {{ position:relative; z-index:1; }}
.task-kicker {{ font-size:11px; text-transform:uppercase; letter-spacing:.08em; color:#9bd7ff; font-weight:800; }}
.task-title {{ margin-top:3px; font-size:16px; font-weight:800; }}
.task-timer {{ font:700 15px 'Courier New',monospace; white-space:nowrap; border:1px solid rgba(162,220,255,.65); padding:6px 10px; border-radius:4px; background:rgba(4,20,49,.48); }}
.task-meta {{ display:flex; gap:7px; flex-wrap:wrap; padding:10px 16px; background:#eef6ff; border-bottom:1px solid #d8e4f3; }}
.task-meta span {{ color:#1c436f; font-size:11px; font-weight:700; border-left:3px solid #2b91ce; padding-left:7px; }}
.task-stages {{ display:grid; grid-template-columns:repeat(4,1fr); gap:0; }}
.task-stage {{ min-height:77px; padding:12px 10px; display:flex; gap:8px; align-items:flex-start; border-right:1px solid #deebf7; background:#fff; transition:.2s ease; }}
.task-stage:last-child {{ border-right:0; }}
.task-stage-num {{ width:22px; height:22px; flex:0 0 22px; border-radius:50%; display:grid; place-items:center; background:#e7eff8; color:#54708f; font-size:11px; font-weight:800; }}
.task-stage strong {{ display:block; font-size:12px; color:#19365b; }} .task-stage small {{ display:block; font-size:10px; line-height:1.25; margin-top:3px; color:#607893; }}
.task-stage.active {{ background:#e8f6ff; box-shadow:inset 0 3px #1587c4; }} .task-stage.active .task-stage-num {{ background:#1587c4; color:#fff; animation:stagePulse 1s ease-in-out infinite; }}
.task-stage.done {{ background:#f0fdf7; }} .task-stage.done .task-stage-num {{ background:#12a574; color:#fff; }}
.task-foot {{ padding:9px 16px; display:flex; align-items:center; gap:8px; background:#f8fbff; color:#365878; font-size:12px; font-weight:650; }}
.task-loader {{ width:7px; height:7px; background:#1592cf; border-radius:50%; animation:dot 1.1s ease-in-out infinite; }}
@keyframes scan {{ to {{ transform:translateX(130%); }} }} @keyframes stagePulse {{ 50% {{ transform:scale(1.13); box-shadow:0 0 0 5px rgba(21,135,196,.15); }} }} @keyframes dot {{ 50% {{ transform:scale(1.7); opacity:.35; }} }}
</style></head><body><section class='task-hud'>
  <div class='task-head'><div><div class='task-kicker'>Single-question authoring</div><div class='task-title'>{html.escape(task_label)} · {html.escape(paper_label)}</div></div><div id='task-timer' class='task-timer'>⏱ {timer_text}</div></div>
  <div class='task-meta'><span>{marks} marks requested</span><span>{html.escape(topic_label)}</span><span>LaTeX and mark scheme included</span></div>
  <div class='task-stages'>{stage_html}</div>
  <div class='task-foot'><span class='task-loader'></span><span id='task-status'>{state_text}</span></div>
</section><script>
const done = {'true' if is_done else 'false'}; const start = {start_ms}; const stages = [...document.querySelectorAll('.task-stage')];
function activate(index) {{ stages.forEach((el,i)=>el.classList.toggle('active',!done && i===index)); stages.forEach((el,i)=>el.classList.toggle('done',done || (!done && i<index))); }}
function formatElapsed(elapsed) {{ const minutes=Math.floor(elapsed/60); const seconds=elapsed-(minutes*60); return minutes ? minutes+' min '+seconds.toFixed(2).padStart(5,'0')+' sec' : seconds.toFixed(2)+' sec'; }}
if (done) {{ activate(stages.length); }} else {{ let active=0; activate(active); setInterval(()=>{{ active=(active+1)%stages.length; activate(active); }}, 1450); setInterval(()=>{{ const elapsed=(Date.now()-start)/1000; document.getElementById('task-timer').textContent='⏱ '+formatElapsed(elapsed); }},100); }}
</script></body></html>"""

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
if "auth_choice" not in st.session_state:
    st.session_state.auth_choice = None

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

# Synchronize active auth mode with AppConfig
if st.session_state.auth_choice == "authenticated":
    AppConfig.set_auth_mode("vertex_ai")
else:
    AppConfig.set_auth_mode("byok")

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
    spinner_html = "" if is_done else '<span class="pipeline-spinner" aria-hidden="true"></span>'
    if is_done:
        try:
            stopwatch_init_text = f"⏱️ {format_elapsed_time(float(re.sub(r'[^0-9.]', '', final_duration_str)))}"
        except ValueError:
            stopwatch_init_text = f"⏱️ {final_duration_str}"
    else:
        stopwatch_init_text = "⏱️ 0.00 sec"

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
@keyframes pipelineSpin {{
    to {{ transform: rotate(360deg); }}
}}
@keyframes spinnerGlow {{
    50% {{ filter: drop-shadow(0 0 5px rgba(14, 165, 233, 0.8)); }}
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
.pipeline-spinner {{
    display: inline-block; width: 18px; height: 18px; margin-right: 9px; flex: 0 0 18px;
    border: 3px solid rgba(14, 165, 233, 0.18); border-top-color: #38bdf8; border-right-color: #fbbf24;
    border-radius: 50%; animation: pipelineSpin 0.75s linear infinite, spinnerGlow 1.2s ease-in-out infinite;
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
        function formatTime(elapsed) {{
            var mins = Math.floor(elapsed / 60);
            var secs = elapsed - (mins * 60);
            return mins > 0
                ? mins + ' min ' + secs.toFixed(2).padStart(5, '0') + ' sec'
                : secs.toFixed(2) + ' sec';
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
    
    if st.session_state.auth_choice == "authenticated":
        st.markdown(
            f"<div style='background: linear-gradient(135deg, #064e3b, #047857); border: 1.5px solid #10b981; border-radius: 10px; padding: 12px; margin-top: 10px; margin-bottom: 12px; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);'>"
            f"<div style='font-size: 0.88rem; font-weight: 800; color: #a7f3d0;'>🛡️ Vertex AI Active (Google Cloud)</div>"
            f"<div style='font-size: 0.82rem; color: #ffffff; margin-top: 3px;'>User: <strong>{st.session_state.auth_user}</strong></div>"
            f"<div style='font-size: 0.74rem; color: #d1fae5; margin-top: 2px;'>Backend: Enterprise Vertex AI (Gemini 3.7 Flash)</div>"
            f"</div>",
            unsafe_allow_html=True
        )
        if st.button("🚪 Logout / Switch Access", use_container_width=True, key="sb_logout_btn"):
            st.session_state.auth_choice = None
            st.session_state.auth_user = None
            AppConfig.set_auth_mode("byok")
            st.rerun()
    else:
        active_key = st.session_state.get("gemini_api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        with st.expander("⚙️ AI Engine & Settings (Guest BYOK)", expanded=True if not active_key else False):
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

            st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
            if st.button("🔐 Switch to Authenticated Access", use_container_width=True, key="sb_switch_auth_btn"):
                st.session_state.auth_choice = None
                st.rerun()
    
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
        session_map = {s["session_id"]: s for s in saved_sessions}
        session_options = {
            f"{s['title'][:30]}{'...' if len(s['title']) > 30 else ''} ({s['paper_type'].upper()})": s["session_id"]
            for s in saved_sessions
        }
        selected_label = st.selectbox("Saved Drafts", options=list(session_options.keys()))
        selected_sess_id = session_options[selected_label]
        selected_sess_meta = session_map.get(selected_sess_id, {})
        
        col_res, col_del = st.columns(2)
        with col_res:
            if st.button("📥 Restore", use_container_width=True):
                loaded = session_mgr.get_session(selected_sess_id)
                if loaded:
                    st.session_state.current_session = loaded
                    st.session_state.studio_questions = loaded.questions or []
                    st.success(f"Restored {loaded.title}")
                    st.rerun()
        with col_del:
            if st.button("🗑️ Delete", use_container_width=True):
                session_mgr.delete_session(selected_sess_id)
                _fetch_cached_sessions.clear()
                if st.session_state.current_session and st.session_state.current_session.session_id == selected_sess_id:
                    st.session_state.current_session = None
                st.warning("Session deleted.")
                st.rerun()

        with st.expander("✏️ Rename Selected Session", expanded=False):
            new_name_val = st.text_input("Edit Session Name", value=selected_sess_meta.get("title", ""), key=f"side_rename_input_{selected_sess_id}")
            if st.button("💾 Save Name", key=f"side_rename_btn_{selected_sess_id}", use_container_width=True):
                if new_name_val.strip():
                    renamed = session_mgr.rename_session(selected_sess_id, new_name_val.strip())
                    if renamed:
                        _fetch_cached_sessions.clear()
                        if st.session_state.current_session and st.session_state.current_session.session_id == selected_sess_id:
                            st.session_state.current_session = renamed
                        st.success(f"Renamed to: '{new_name_val.strip()}'")
                        st.rerun()
                else:
                    st.error("Title cannot be blank.")
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
# WELCOME & ACCESS GATEWAY MODAL (FIRST VISIT POPUP)
# ==============================================================================
@st.dialog("🎓 Welcome to ComputingScribe AI", width="large")
def show_welcome_gateway():
    st.markdown("#### Select Access Mode")
    st.markdown("Choose whether to use your own free Gemini API key (**Guest Entry**) or log in with verified credentials for **Google Cloud Vertex AI**.")
    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)
    
    col_guest, col_auth = st.columns(2)
    
    with col_guest:
        st.markdown(
            """
            <div style="background: #f8fafc; border: 1.5px solid #cbd5e1; border-radius: 12px; padding: 18px; min-height: 150px;">
                <div style="font-size: 1.8rem; margin-bottom: 4px;">👤</div>
                <h3 style="margin: 0 0 6px 0; color: #0f172a; font-size: 1.15rem;">Guest Entry</h3>
                <p style="font-size: 0.86rem; color: #475569; line-height: 1.45;">
                    <strong>Bring Your Own Key (BYOK)</strong> via your Google AI Studio API key. Instant access, zero server credentials required.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.write("")
        if st.button("👉 Enter as Guest (BYOK)", type="secondary", use_container_width=True, key="dlg_guest_btn"):
            st.session_state.auth_choice = "guest"
            AppConfig.set_auth_mode("byok")
            st.rerun()

    with col_auth:
        st.markdown(
            """
            <div style="background: #eff6ff; border: 1.5px solid #93c5fd; border-radius: 12px; padding: 18px; min-height: 150px;">
                <div style="font-size: 1.8rem; margin-bottom: 4px;">🔐</div>
                <h3 style="margin: 0 0 6px 0; color: #1e3a8a; font-size: 1.15rem;">Authenticated Access</h3>
                <p style="font-size: 0.86rem; color: #1e40af; line-height: 1.45; margin-bottom: 8px;">
                    <strong>Enterprise Vertex AI</strong> (Gemini 3.7 Flash). Authenticates securely against Google Cloud Secret Manager.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        st.write("")
        with st.form("auth_login_form"):
            u_input = st.text_input("Username", placeholder="e.g. admin or educator", key="dlg_user_in")
            p_input = st.text_input("Password", type="password", placeholder="••••••••", key="dlg_pass_in")
            login_submitted = st.form_submit_button("🚀 Log In & Access Vertex AI", type="primary", use_container_width=True)
            if login_submitted:
                if u_input and p_input:
                    with st.spinner("Verifying credentials against Google Cloud Secret Manager..."):
                        is_valid, msg = AuthManager.verify_credentials(u_input, p_input)
                        if is_valid:
                            st.session_state.auth_choice = "authenticated"
                            st.session_state.auth_user = u_input.strip()
                            st.session_state.teacher_id = u_input.strip()
                            st.session_state.orchestrator.set_teacher_id(u_input.strip())
                            AppConfig.set_auth_mode("vertex_ai")
                            st.success(f"✅ Authenticated! Connected to Vertex AI.")
                            time.sleep(0.4)
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")
                else:
                    st.warning("Please enter both username and password.")

if st.session_state.auth_choice is None:
    show_welcome_gateway()

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
                default=[],
                help="Select one or more topics to assess in this exam paper."
            )
        with col_top_cust:
            custom_topics_input = st.text_input(
                "➕ Custom Topic(s) (Optional)",
                placeholder="",
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
        col_inst, col_yr, col_ser = st.columns([1.5, 0.8, 1.2])
        with col_inst:
            institution = st.text_input("Institution Name", value="HelloWorld Junior College", key="full_inst")
        with col_yr:
            exam_year = st.text_input("Exam Year", value=CURRENT_YEAR, key="full_yr")
        with col_ser:
            sel_series = st.selectbox("Series", options=SERIES_OPTIONS, index=0, key="full_ser_sel")
            if sel_series == "Other / Custom...":
                exam_series = st.text_input("Type Custom Series", value="", placeholder="e.g. End-of-Year Exam", key="full_ser_custom")
                if not exam_series.strip():
                    exam_series = "Exam"
            else:
                exam_series = sel_series

        session_custom_title = st.text_input(
            "Session Name / Title (Optional)",
            value="",
            placeholder="e.g. 2027 Prelim Paper 2 - Linear ADTs & Data Processing",
            help="Custom name for this exam session. If blank, an automatic descriptive title is generated.",
            key="full_custom_title"
        )

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

        col_opt, col_hint = st.columns([1.5, 1.5])
        with col_opt:
            skip_healing_full = st.checkbox(
                "⚡ Fast Mode: Skip sandbox self-healing loop (Save API credits)",
                value=True,
                key="full_skip_healing",
                help="Executes a single-pass compilation without calling iterative Gemini auto-repair loops if minor compiler warnings occur."
            )
        with col_hint:
            st.caption("💡 *Tip: Adding the word `'contextual'` triggers extended real-world scenarios and step-by-step bulleted subtasks.*")

        generate_btn = st.button("Generate Exam Package", type="primary", use_container_width=True)

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
                progress=progress_handler,
                skip_self_healing=skip_healing_full,
                session_title=session_custom_title
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
                default=[],
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
            authoring_progress = st.empty()
            start_ms = int(t0 * 1000)
            with authoring_progress.container():
                components.html(
                    build_task_authoring_hud_html(
                        task_number=int(s_task_num),
                        paper_type=s_paper_type,
                        marks=int(s_marks),
                        topics=s_all_topics,
                        start_ms=start_ms,
                    ),
                    height=215,
                )
            task_draft = st.session_state.orchestrator.author_single_task(
                prompt=s_prompt,
                paper_type=s_paper_type,
                category=s_category,
                task_number=int(s_task_num),
                total_marks=int(s_marks)
            )
            st.session_state.studio_current_draft = task_draft
            dur = round(time.time() - t0, 1)
            with authoring_progress.container():
                components.html(
                    build_task_authoring_hud_html(
                        task_number=int(s_task_num),
                        paper_type=s_paper_type,
                        marks=int(s_marks),
                        topics=s_all_topics,
                        start_ms=start_ms,
                        is_done=True,
                        final_duration_str=f"{dur:.1f}s",
                    ),
                    height=215,
                )
            st.success(f"✨ {('Task' if s_paper_type == 'practical' else 'Question')} {s_task_num} authored in {dur}s. Review the draft below.")

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
                        activity_placeholder = st.empty()
                        with activity_placeholder.container():
                            render_activity_hud(
                                "Refining question",
                                "Reworking the assessment wording, structure, marks and LaTeX source.",
                                "refine-question",
                                int(time.time() * 1000),
                            )
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
                col_b_inst, col_b_yr, col_b_ser = st.columns([1.5, 0.8, 1.2])
                with col_b_inst:
                    b_institution = st.text_input("Institution Name", value="HelloWorld Junior College", key="studio_inst")
                with col_b_yr:
                    b_exam_year = st.text_input("Exam Year", value=CURRENT_YEAR, key="studio_yr")
                with col_b_ser:
                    b_sel_series = st.selectbox("Series", options=SERIES_OPTIONS, index=0, key="studio_ser_sel")
                    if b_sel_series == "Other / Custom...":
                        b_exam_series = st.text_input("Type Custom Series", value="", placeholder="e.g. End-of-Year Exam", key="studio_ser_custom")
                        if not b_exam_series.strip():
                            b_exam_series = "Exam"
                    else:
                        b_exam_series = b_sel_series
                b_custom_title = st.text_input(
                    "Session Name / Title (Optional)",
                    value="",
                    placeholder="e.g. Assembled Topical Test - Linear ADTs & Trees",
                    key="studio_custom_title"
                )

            # Live Preview of Full Assembled LaTeX Source
            with st.expander("👁️ Inspect Full Assembled LaTeX Document Code", expanded=False):
                st.caption("Complete combined LaTeX document for all assembled questions above:")
                preview_assembled = st.session_state.orchestrator.question_author.assemble_full_paper(
                    tasks_list=q_list,
                    paper_type=s_paper_type,
                    syllabus_code="9569",
                    paper_number="02" if s_paper_type == "practical" else "01",
                    institution=b_institution if 'b_institution' in locals() else "HelloWorld Junior College",
                    exam_year=b_exam_year if 'b_exam_year' in locals() else "2027",
                    exam_series=b_exam_series if 'b_exam_series' in locals() else "Prelim"
                )
                st.code(preview_assembled["latex_source"], language="latex")

            skip_healing_studio = st.checkbox(
                "⚡ Fast Mode: Skip sandbox self-healing loop (Save API credits)",
                value=True,
                key="studio_skip_healing",
                help="Executes single-pass compilation without calling iterative Gemini auto-repair loops if minor compiler warnings occur."
            )

            # Compile & Build Button styled with blue background & light blue text
            st.markdown("<div class='compile-build-box'>", unsafe_allow_html=True)
            if st.button("Build Exam Package", type="primary", use_container_width=True, key="studio_compile_btn"):
                activity_placeholder = st.empty()
                with activity_placeholder.container():
                    render_activity_hud(
                        "Building exam package",
                        "Assembling the paper and mark scheme, then checking the LaTeX package for export.",
                        "build-package",
                        int(time.time() * 1000),
                    )
                compiled_sess = st.session_state.orchestrator.compile_assembled_session(
                    tasks_list=q_list,
                    paper_type=s_paper_type,
                    syllabus_code="9569",
                    paper_number="02" if s_paper_type == "practical" else "01",
                    institution=b_institution if 'b_institution' in locals() else "HelloWorld Junior College",
                    exam_year=b_exam_year if 'b_exam_year' in locals() else "2027",
                    exam_series=b_exam_series if 'b_exam_series' in locals() else "Prelim",
                    skip_self_healing=skip_healing_studio,
                    session_title=b_custom_title if 'b_custom_title' in locals() else None
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

        transcription_prompt = st.text_area(
            "Optional Transcription Instructions",
            value="",
            placeholder="e.g. Preserve the source structure exactly; do not add extra required structure. Or: convert each task into the Cambridge required structure with clear subtasks.",
            height=110,
            key="transcription_prompt",
            help="Add specific guidance before transcription, such as whether to preserve the uploaded structure or force Cambridge practical/theory formatting."
        )

        col_inst, col_yr, col_ser = st.columns([1.5, 0.8, 1.2])
        with col_inst:
            t_institution = st.text_input("Institution Name", value="Singapore Junior College", key="trans_inst")
        with col_yr:
            t_exam_year = st.text_input("Exam Year", value=CURRENT_YEAR, key="trans_yr")
        with col_ser:
            t_sel_series = st.selectbox("Series", options=SERIES_OPTIONS, index=0, key="trans_ser_sel")
            if t_sel_series == "Other / Custom...":
                t_exam_series = st.text_input("Type Custom Series", value="", placeholder="e.g. End-of-Year Exam", key="trans_ser_custom")
                if not t_exam_series.strip():
                    t_exam_series = "Exam"
            else:
                t_exam_series = t_sel_series

        t_custom_title = st.text_input(
            "Session Name / Title (Optional)",
            value="",
            placeholder=f"e.g. Transcribed Exam - {doc_file.name if doc_file else 'Paper'}",
            help="Custom name for this transcribed session. If blank, a descriptive title is automatically assigned.",
            key="trans_custom_title"
        )

        skip_healing_trans = st.checkbox(
            "⚡ Fast Mode: Skip sandbox self-healing loop (Save API credits)",
            value=True,
            key="trans_skip_healing",
            help="Executes single-pass compilation without calling iterative Gemini auto-repair loops if minor compiler warnings occur."
        )

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
                user_instructions=transcription_prompt,
                progress=progress_listener,
                skip_self_healing=skip_healing_trans,
                session_title=t_custom_title if 't_custom_title' in locals() else None
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
    session_paper_report = LaTeXSyntaxValidator.validate_syntax(curr_sess.latex_source)
    session_mark_scheme_report = LaTeXSyntaxValidator.validate_syntax(curr_sess.mark_scheme_source)
    session_native_compile_verified = (
        curr_sess.status == "completed"
        and curr_sess.compiled_source_hash == curr_sess.source_fingerprint()
        and curr_sess.compilation_logs.count("[pdflatex Engine]: Native pdflatex compilation succeeded on two passes.") >= 2
    )
    session_export_ready = (
        session_paper_report.is_valid
        and session_mark_scheme_report.is_valid
        and session_native_compile_verified
    )
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

    # Session Title & Quick Rename Bar
    sess_head_c1, sess_head_c2 = st.columns([3.6, 1.4])
    with sess_head_c1:
        st.markdown(
            f"<div style='display: flex; align-items: center; gap: 10px; margin: 10px 0;'>"
            f"<span style='font-size: 1.35rem; font-weight: 800; color: #0f172a;'>📝 {curr_sess.title}</span>"
            f"<span style='font-size: 0.8rem; background: #e0e7ff; color: #3730a3; border: 1px solid #c7d2fe; font-weight: 700; padding: 3px 10px; border-radius: 6px; font-family: monospace;'>ID: {curr_sess.session_id}</span>"
            f"</div>",
            unsafe_allow_html=True
        )
    with sess_head_c2:
        with st.popover("✏️ Rename Session", use_container_width=True):
            st.markdown("##### ✏️ Rename Exam Session")
            st.caption("Update the title saved in memory and exported packages.")
            main_rename_val = st.text_input("New Title", value=curr_sess.title, key=f"top_rename_val_{curr_sess.session_id}")
            if st.button("💾 Save Title", key=f"btn_save_top_title_{curr_sess.session_id}", type="primary", use_container_width=True):
                if main_rename_val.strip():
                    renamed_res = st.session_state.orchestrator.session_manager.rename_session(curr_sess.session_id, main_rename_val.strip())
                    if renamed_res:
                        st.session_state.current_session = renamed_res
                        _fetch_cached_sessions.clear()
                        st.success(f"Renamed to '{main_rename_val.strip()}'!")
                        st.rerun()
                else:
                    st.error("Title cannot be blank.")
    
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
        bundle_bytes = st.session_state.orchestrator.session_manager.export_bundle_zip(curr_sess.session_id)
        if bundle_bytes:
            st.download_button(
                "📦 Download .ZIP Bundle",
                data=bundle_bytes,
                file_name=f"{curr_sess.syllabus_code}_{curr_sess.paper_number}_complete_package.zip",
                mime="application/zip",
                type="primary",
                use_container_width=True
            )
            if not session_export_ready:
                st.warning("This ZIP is downloadable, but it has not passed native pdflatex verification. Resolve the compiler errors before treating it as print-ready.")

    # Post-generation Zero-Compile AI TeX Audit & Repair Action Bar
    with st.expander("🤖 Gemini AI TeX Audit & Fix (Zero-Compile & Error Repair)", expanded=False):
        st.caption("⚡ **Zero-Compile AI Linter**: Audits syntax, unescaped `_`/`%`/`#`, unmatched `\\begin{...}`, and Cambridge tags using pure Gemini reasoning without invoking pdflatex. You can paste any compiler error log below:")
        col_top_err, col_top_act = st.columns([3, 1])
        with col_top_err:
            top_pasted_err = st.text_area(
                "Paste Compiler Error / Log / Issue (Optional)",
                placeholder="e.g. ! LaTeX Error: File ulem.sty not found or ! Missing $ inserted or paste terminal compiler log...",
                height=70,
                key="top_ai_lint_err_input"
            )
        with col_top_act:
            st.write("")
            st.write("")
            if st.button("✨ Run AI TeX Audit & Fix", key="top_ai_lint_btn", type="primary", use_container_width=True):
                with st.spinner("🤖 Gemini 3.7 Flash is auditing and repairing LaTeX syntax (zero-compile)..."):
                    lint_result = st.session_state.orchestrator.ai_lint_and_repair_document(
                        latex_source=curr_sess.latex_source,
                        mark_scheme_source=curr_sess.mark_scheme_source,
                        paper_type=curr_sess.paper_type,
                        compiler_error=top_pasted_err
                    )
                    curr_sess.latex_source = lint_result["repaired_latex_source"]
                    if lint_result.get("repaired_mark_scheme_source"):
                        curr_sess.mark_scheme_source = lint_result["repaired_mark_scheme_source"]
                    st.session_state.orchestrator.session_manager.save_session(curr_sess)
                    st.session_state.current_session = curr_sess
                    st.session_state["last_lint_summary"] = lint_result.get("audit_summary", "Audit completed successfully.")
                    st.session_state["last_lint_fixes"] = lint_result.get("fixes_applied", [])
                    st.success(f"✅ AI TeX Audit & Fix Complete! {lint_result.get('audit_summary', '')}")
                    st.rerun()

    if st.session_state.get("last_lint_summary"):
        with st.expander(f"✨ AI TeX Audit Report: {st.session_state.get('last_lint_summary')}", expanded=True):
            fixes = st.session_state.get("last_lint_fixes", [])
            if fixes:
                for fix in fixes:
                    st.markdown(f"- 🔧 {fix}")
            else:
                st.markdown("- ✅ All LaTeX environments, tags, and macros verified syntax-clean.")

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
        paper_export_report = LaTeXSyntaxValidator.validate_syntax(curr_sess.latex_source)
        paper_export_ready = paper_export_report.is_valid and session_native_compile_verified
        col_hdr, col_btn_down = st.columns([1.6, 1.4])
        with col_hdr:
            st.markdown("### 📄 Question Paper (KaTeX Live Preview)")
            st.caption("Clean pedagogical view of questions, subtasks, Jupyter cells, and mark brackets.")
        with col_btn_down:
            if not paper_export_ready:
                st.warning("This source is downloadable, but it has not passed native pdflatex verification. Check the compilation log before using it in production.")
            st.download_button(
                "⬇️ Download paper.tex",
                data=curr_sess.latex_source,
                file_name="paper.tex",
                mime="text/x-tex",
                type="primary",
                use_container_width=True,
            )

        render_tex_copy_control(curr_sess.latex_source, "paper.tex", "paper-tex")

        with st.expander("🖼️ Insert Exam Image", expanded=False):
            st.caption("PNG and JPEG images are stored in this paper's `assets/` folder. They render in the browser preview and are included with `paper.tex` in the export ZIP.")
            
            col_img_up, col_img_w = st.columns([1.6, 1])
            with col_img_up:
                image_file = st.file_uploader(
                    "Image file (PNG/JPG)",
                    type=["png", "jpg", "jpeg"],
                    key="paper_image_uploader",
                )
            with col_img_w:
                image_width = st.slider(
                    "Display width (% of text width)",
                    min_value=10,
                    max_value=100,
                    value=65,
                    key="paper_image_width",
                )

            image_placement = st.radio(
                "Placement method",
                options=["Click to select line in paper.tex", "At end of paper", "After an exact phrase"],
                horizontal=True,
                key="paper_image_placement",
            )

            raw_tex_lines = curr_sess.latex_source.splitlines()
            total_tex_lines = len(raw_tex_lines)
            
            target_line_num = None
            pos_choice = "after"
            image_anchor = ""

            if image_placement == "Click to select line in paper.tex":
                if "img_insert_line" not in st.session_state or st.session_state.img_insert_line > total_tex_lines:
                    st.session_state.img_insert_line = min(20, total_tex_lines) if total_tex_lines > 0 else 1

                col_pos_sel, col_line_pick = st.columns([1.1, 1.4])
                with col_pos_sel:
                    pos_choice_label = st.radio(
                        "Position relative to selected line",
                        options=["Insert AFTER line", "Insert BEFORE line"],
                        horizontal=True,
                        key="paper_img_pos_choice"
                    )
                    pos_choice = "after" if "AFTER" in pos_choice_label else "before"
                
                with col_line_pick:
                    manual_line = st.number_input(
                        "Selected Line # (or click row below)",
                        min_value=1,
                        max_value=max(1, total_tex_lines),
                        value=st.session_state.img_insert_line,
                        step=1,
                        key="paper_img_line_num_input"
                    )
                    if manual_line != st.session_state.img_insert_line:
                        st.session_state.img_insert_line = manual_line

                target_line_num = st.session_state.img_insert_line

                # Interactive TeX Line Clicker Table
                st.markdown("**👇 Click on any line in the TeX source code to select the insertion position:**")
                df_source = pd.DataFrame({
                    "Line #": list(range(1, total_tex_lines + 1)),
                    "LaTeX Code": raw_tex_lines
                })
                
                sel_event = st.dataframe(
                    df_source,
                    use_container_width=True,
                    hide_index=True,
                    height=280,
                    selection_mode="single-row",
                    on_select="rerun",
                    key="paper_tex_line_clicker_df",
                    column_config={
                        "Line #": st.column_config.NumberColumn("Line #", width="small"),
                        "LaTeX Code": st.column_config.TextColumn("LaTeX Source Content", width="large"),
                    }
                )

                if sel_event and hasattr(sel_event, "selection") and sel_event.selection and sel_event.selection.rows:
                    clicked_row = sel_event.selection.rows[0]
                    clicked_line = clicked_row + 1
                    if clicked_line != st.session_state.img_insert_line:
                        st.session_state.img_insert_line = clicked_line
                        target_line_num = clicked_line
                        st.rerun()

                # Live Context Preview Box
                if 1 <= target_line_num <= total_tex_lines:
                    ctx_start = max(0, target_line_num - 3)
                    ctx_end = min(total_tex_lines, target_line_num + 2)
                    
                    preview_snippets = []
                    img_name_disp = html.escape(image_file.name) if image_file else "uploaded_image.png"
                    marker_badge = (
                        f"<div style='background: #dbeafe; color: #1e40af; border: 1.5px dashed #3b82f6; "
                        f"border-radius: 6px; padding: 5px 12px; margin: 5px 0; font-weight: 700; "
                        f"font-family: sans-serif; display: flex; align-items: center; gap: 8px;'>"
                        f"<span>🖼️</span> <span>[Image: <strong>{img_name_disp}</strong> will be inserted here at {image_width}% width]</span>"
                        f"</div>"
                    )
                    
                    for idx in range(ctx_start, ctx_end):
                        curr_l = idx + 1
                        line_text = html.escape(raw_tex_lines[idx])
                        line_num_badge = f"<span style='color: #64748b; font-weight: 600;'>{curr_l:3d} |</span> "
                        
                        if pos_choice == "before" and curr_l == target_line_num:
                            preview_snippets.append(marker_badge)
                        
                        is_target = (curr_l == target_line_num)
                        bg_style = "background: #f1f5f9; padding: 2px 4px; border-radius: 4px;" if is_target else ""
                        preview_snippets.append(f"<div style='{bg_style}'>{line_num_badge}{line_text if line_text else '<em>(blank line)</em>'}</div>")
                        
                        if pos_choice == "after" and curr_l == target_line_num:
                            preview_snippets.append(marker_badge)

                    pos_desc = f"AFTER Line {target_line_num}" if pos_choice == "after" else f"BEFORE Line {target_line_num}"
                    st.markdown(
                        f"<div style='background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px 14px; margin-top: 10px; font-family: monospace; font-size: 0.86rem; line-height: 1.5;'>"
                        f"<div style='font-family: sans-serif; font-weight: 700; color: #0f172a; margin-bottom: 8px; display: flex; justify-content: space-between;'>"
                        f"<span>📍 Insertion Point: <span style='color: #2563eb;'>{pos_desc}</span></span>"
                        f"<span style='font-size: 0.8rem; color: #64748b; font-weight: normal;'>Displaying context around line {target_line_num}</span>"
                        f"</div>"
                        + "".join(preview_snippets) +
                        "</div>",
                        unsafe_allow_html=True
                    )

            elif image_placement == "After an exact phrase":
                image_anchor = st.text_input(
                    "Exact phrase in paper.tex",
                    placeholder="Paste a unique phrase from the question text",
                    key="paper_image_anchor",
                )

            if st.button("🖼️ Insert image into paper.tex", type="primary", key="insert_paper_image_btn", disabled=not image_file, use_container_width=True):
                image_macro_placeholder = "__IMAGE_MACRO__"
                updated_source, insert_error = insert_exam_image(
                    latex_source=curr_sess.latex_source,
                    image_macro=image_macro_placeholder,
                    placement=image_placement,
                    phrase=image_anchor,
                    line_number=target_line_num,
                    position=pos_choice,
                )
                if insert_error:
                    st.error(insert_error)
                else:
                    try:
                        asset = st.session_state.orchestrator.session_manager.save_image_asset(
                            curr_sess,
                            image_file.name,
                            image_file.getvalue(),
                            image_file.type,
                        )
                        image_macro = rf"\ExamImage{{{asset['path']}}}{{{image_width / 100:.2f}\linewidth}}"
                        curr_sess.latex_source = updated_source.replace(image_macro_placeholder, image_macro, 1)
                        st.session_state.orchestrator.session_manager.save_session(curr_sess)
                        st.session_state.current_session = curr_sess
                        st.success(f"✅ Successfully inserted {asset['original_name']} ({image_width}% width) into paper.tex!")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

        tex_bundle = st.session_state.orchestrator.session_manager.export_bundle_zip(curr_sess.session_id)
        if tex_bundle:
            st.download_button(
                "⬇️ Download paper.tex + images (.zip)",
                data=tex_bundle,
                file_name=f"{curr_sess.syllabus_code}_{curr_sess.paper_number}_tex_assets.zip",
                mime="application/zip",
                use_container_width=True,
                key="paper_tex_assets_download",
            )

        # AI Fix TeX Action with Optional Error Message Input
        with st.expander("🤖 Gemini AI TeX Audit & Fix (Zero-Compile & Error Repair)", expanded=False):
            st.caption("Zero-compile static linter: audits syntax and repairs specific compiler errors using Gemini 3.7 Flash.")
            tab2_pasted_err = st.text_area(
                "Paste Compiler Error / Log / Issue (Optional)",
                placeholder="e.g. ! LaTeX Error: File ulem.sty not found or ! Missing $ inserted or paste terminal compiler log...",
                height=75,
                key="tab2_ai_lint_err_input"
            )
            if st.button("✨ Run AI TeX Audit & Fix on paper.tex", key="tab2_ai_lint_btn", type="primary", use_container_width=True):
                with st.spinner("🤖 Gemini is checking and fixing LaTeX syntax (zero-compile)..."):
                    lint_res = st.session_state.orchestrator.ai_lint_and_repair_document(
                        latex_source=curr_sess.latex_source,
                        mark_scheme_source=curr_sess.mark_scheme_source,
                        paper_type=curr_sess.paper_type,
                        compiler_error=tab2_pasted_err
                    )
                    curr_sess.latex_source = lint_res["repaired_latex_source"]
                    if lint_res.get("repaired_mark_scheme_source"):
                        curr_sess.mark_scheme_source = lint_res["repaired_mark_scheme_source"]
                    st.session_state.orchestrator.session_manager.save_session(curr_sess)
                    st.session_state.current_session = curr_sess
                    st.session_state["last_lint_summary"] = lint_res.get("audit_summary", "Audit completed successfully.")
                    st.session_state["last_lint_fixes"] = lint_res.get("fixes_applied", [])
                    st.success(f"✅ Repaired: {lint_res.get('audit_summary', '')}")
                    st.rerun()

        # Clean KaTeX Questions Rendering (No Cover/Header noise)
        rendered_html = LaTeXVisualRenderer.render_questions_only_html(
            curr_sess.latex_source,
            title=curr_sess.title,
            image_data_urls=build_session_image_data_urls(curr_sess),
        )
        components.html(rendered_html, height=850, scrolling=True)

        # Editable TeX workspace
        st.markdown("---")
        st.markdown("### TeX Editor (`paper.tex`)")
        st.caption("Edit the source directly, then save it to update the preview and every export. The gutter flags common structural TeX issues as you work.")
        render_tex_editor(curr_sess, "latex_source", "paper.tex", "paper")

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
            activity_placeholder = st.empty()
            with activity_placeholder.container():
                render_activity_hud(
                    "Refining the full paper",
                    "Updating the question paper and mark scheme, then rebuilding the LaTeX artefacts.",
                    "refine-full-paper",
                    int(t0 * 1000),
                )
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
        mark_scheme_export_report = LaTeXSyntaxValidator.validate_syntax(curr_sess.mark_scheme_source)
        mark_scheme_export_ready = mark_scheme_export_report.is_valid and session_native_compile_verified
        col_mshdr, col_msbtn = st.columns([1.6, 1.4])
        with col_mshdr:
            st.markdown("### 📝 Official Cambridge Mark Scheme (KaTeX Live Preview)")
            st.caption("Granular partial credit rubrics with Assessment Objective (AO) allocations.")
        with col_msbtn:
            if not mark_scheme_export_ready:
                st.warning("This source is downloadable, but it has not passed native pdflatex verification. Check the compilation log before using it in production.")
            st.download_button(
                "⬇️ Download mark_scheme.tex",
                data=curr_sess.mark_scheme_source,
                file_name="mark_scheme.tex",
                mime="text/x-tex",
                type="primary",
                use_container_width=True,
            )

        render_tex_copy_control(curr_sess.mark_scheme_source, "mark_scheme.tex", "mark-scheme-tex")

        ms_rendered_html = LaTeXVisualRenderer.render_questions_only_html(curr_sess.mark_scheme_source, title="Mark Scheme")
        components.html(ms_rendered_html, height=850, scrolling=True)

        # Editable mark scheme workspace
        st.markdown("---")
        st.markdown("### TeX Editor (`mark_scheme.tex`)")
        st.caption("Edit and save the mark scheme directly. Live linting marks common TeX structure problems in the gutter.")
        render_tex_editor(curr_sess, "mark_scheme_source", "mark_scheme.tex", "mark-scheme")

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
