"""
EduScribe AI - LaTeX Visual Typesetting & Sheet Renderer
Renders Cambridge Examination LaTeX papers and Mark Schemes into publication-grade,
pixel-perfect A4 exam sheets with math, tables, pseudocode, Jupyter cells, and mark brackets.
"""

import re
import html
from typing import Dict, Any, List

class LaTeXVisualRenderer:
    @staticmethod
    def render_to_html(latex_source: str, title: str = "Examination Paper") -> str:
        """
        Transforms Cambridge LaTeX source into a publication-grade A4 Exam Paper sheet.
        Supports Jupyter cells, pseudocode listings, decision tables, and right-aligned mark brackets.
        """
        # Extract macros
        institution = "Anderson Serangoon Junior College"
        inst_m = re.search(r"\\newcommand\{\\Institution\}\{([^}]+)\}", latex_source)
        if inst_m:
            institution = inst_m.group(1)

        syllabus_code = "9569"
        syl_m = re.search(r"\\newcommand\{\\SyllabusCode\}\{([^}]+)\}", latex_source)
        if syl_m:
            syllabus_code = syl_m.group(1)

        paper_num = "02"
        p_m = re.search(r"\\newcommand\{\\PaperNumber\}\{([^}]+)\}", latex_source)
        if p_m:
            paper_num = p_m.group(1)

        exam_year = "2027"
        y_m = re.search(r"\\newcommand\{\\ExamYear\}\{([^}]+)\}", latex_source)
        if y_m:
            exam_year = y_m.group(1)

        exam_series = "PRELIM"
        es_m = re.search(r"\\newcommand\{\\ExamSeries\}\{([^}]+)\}", latex_source)
        if es_m:
            exam_series = es_m.group(1)

        # Extract document body
        body_match = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", latex_source, re.DOTALL)
        body_text = body_match.group(1) if body_match else latex_source

        # Split into pages by \newpage
        raw_pages = body_text.split(r"\newpage")
        
        pages_html = []
        page_counter = 2
        
        for p_idx, raw_page in enumerate(raw_pages, start=2):
            content_html = LaTeXVisualRenderer._process_page_content(raw_page)
            if not content_html.strip():
                continue

            page_html = f"""
            <div class="exam-page">
                <div class="exam-header">
                    <div class="exam-header-left"><strong>{institution}</strong></div>
                    <div class="exam-header-center"><strong>{page_counter}</strong></div>
                    <div class="exam-header-right">{syllabus_code}/{paper_num}/{exam_series}/{exam_year[-2:]}</div>
                </div>
                <div class="exam-body">
                    {content_html}
                </div>
                <div class="exam-footer">
                    <div class="exam-footer-left">&copy; {institution} {exam_year}</div>
                    <div class="exam-footer-center">{syllabus_code}/{paper_num}/{exam_series}/{exam_year[-2:]}</div>
                    <div class="exam-footer-right"><strong>[Turn over</strong></div>
                </div>
            </div>
            """
            pages_html.append(page_html)
            page_counter += 1

        all_pages_str = "\n".join(pages_html)

        html_doc = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
            <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js"></script>
            <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js"
                onload="renderMathInElement(document.body);"></script>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Arial:wght@400;700&family=Courier+Prime&display=swap');
                
                body {{
                    font-family: Arial, sans-serif;
                    background-color: #f1f5f9;
                    margin: 0;
                    padding: 20px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    color: #0f172a;
                }}
                
                .exam-page {{
                    background: #ffffff;
                    width: 210mm;
                    min-height: 297mm;
                    padding: 20mm 20mm 25mm 20mm;
                    margin-bottom: 25px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
                    box-sizing: border-box;
                    position: relative;
                    font-size: 11pt;
                    line-height: 1.5;
                }}
                
                .exam-header {{
                    display: flex;
                    justify-content: space-between;
                    border-bottom: 1px solid #94a3b8;
                    padding-bottom: 6px;
                    margin-bottom: 18px;
                    font-size: 9pt;
                    color: #475569;
                }}
                
                .exam-footer {{
                    position: absolute;
                    bottom: 12mm;
                    left: 20mm;
                    right: 20mm;
                    display: flex;
                    justify-content: space-between;
                    border-top: 1px solid #94a3b8;
                    padding-top: 6px;
                    font-size: 8.5pt;
                    color: #475569;
                }}
                
                .maintask-title {{
                    font-size: 12pt;
                    font-weight: bold;
                    margin-top: 16px;
                    margin-bottom: 6px;
                    color: #0f172a;
                }}
                
                .subtask-title {{
                    font-size: 11pt;
                    font-weight: bold;
                    margin-top: 14px;
                    margin-bottom: 4px;
                    color: #0f172a;
                }}
                
                .marks-bracket {{
                    float: right;
                    font-weight: normal;
                    color: #0f172a;
                    margin-left: 10px;
                }}
                
                .jupyter-box {{
                    display: flex;
                    align-items: flex-start;
                    margin: 12px 0;
                    font-family: 'Courier Prime', monospace;
                    font-size: 10pt;
                }}
                
                .jupyter-label {{
                    width: 75px;
                    font-weight: bold;
                    color: #334155;
                }}
                
                .jupyter-code {{
                    flex: 1;
                    background-color: #f1f5f9;
                    border: 1px solid #000000;
                    padding: 8px 12px;
                    white-space: pre-wrap;
                    font-style: italic;
                }}
                
                .pseudocode-box {{
                    background: #f8fafc;
                    border: 1px solid #cbd5e1;
                    border-left: 4px solid #2563eb;
                    padding: 12px 16px;
                    margin: 14px 0;
                    font-family: 'Courier Prime', monospace;
                    font-size: 10pt;
                    line-height: 1.4;
                }}
                
                .pseudo-line {{
                    display: flex;
                }}
                
                .line-num {{
                    width: 32px;
                    color: #64748b;
                    user-select: none;
                    font-weight: bold;
                }}
                
                .exam-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 14px 0;
                    font-size: 10pt;
                }}
                
                .exam-table th, .exam-table td {{
                    border: 1px solid #000000;
                    padding: 6px 10px;
                    text-align: left;
                    vertical-align: top;
                }}
                
                .exam-table th {{
                    background-color: #f1f5f9;
                    font-weight: bold;
                }}
                
                code, .inline-code {{
                    font-family: 'Courier Prime', monospace;
                    background: #f1f5f9;
                    padding: 1px 4px;
                    border-radius: 3px;
                    font-size: 9.5pt;
                }}
                
                .testcases-list {{
                    margin: 8px 0 8px 20px;
                    list-style-type: square;
                }}
                
                .clearfix::after {{
                    content: "";
                    clear: both;
                    display: table;
                }}
            </style>
        </head>
        <body>
            {all_pages_str}
        </body>
        </html>
        """
        return html_doc

    @staticmethod
    def _process_page_content(tex_chunk: str) -> str:
        """Processes LaTeX commands inside a page chunk into clean semantic HTML."""
        lines = tex_chunk.splitlines()
        html_out = []
        in_pseudocode = False
        pseudo_lines = []
        in_table = False
        table_rows = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("%"):
                continue
            if line.startswith(r"\setcounter") or line.startswith(r"\TurnOver") or line.startswith(r"\NoTurnOver"):
                continue

            # Check for Pseudocode Block
            if r"\begin{pseudocode}" in line:
                in_pseudocode = True
                pseudo_lines = []
                continue
            if r"\end{pseudocode}" in line:
                in_pseudocode = False
                p_html = "<div class='pseudocode-box'>"
                for idx, pl in enumerate(pseudo_lines, start=1):
                    p_html += f"<div class='pseudo-line'><span class='line-num'>{idx:02d}</span><span>{html.escape(pl)}</span></div>"
                p_html += "</div>"
                html_out.append(p_html)
                continue
            if in_pseudocode:
                pseudo_lines.append(raw_line)
                continue

            # Check for Main Tasks
            if r"\maintask{" in line:
                m = re.search(r"\\maintask\{([^}]+)\}", line)
                t_val = m.group(1) if m else ""
                html_out.append(f"<div class='maintask-title'>Task {t_val}</div>")
                continue

            # Check for Sub Tasks
            if r"\subtask{" in line:
                m = re.search(r"\\subtask\{([^}]+)\}", line)
                s_val = m.group(1) if m else ""
                html_out.append(f"<div class='subtask-title'>Task {s_val}</div>")
                continue

            # Check for Jupyter Cells
            if r"\jupytercell{" in line:
                m = re.search(r"\\jupytercell\{([^}]+)\}\{([^}]+)\}", line)
                if m:
                    in_num = m.group(1)
                    code_text = m.group(2).replace(r"\\", "\n")
                    html_out.append(f"""
                    <div class="jupyter-box">
                        <div class="jupyter-label">In [{in_num}]:</div>
                        <div class="jupyter-code">{html.escape(code_text)}</div>
                    </div>
                    <div style="margin-left: 75px; font-family: 'Courier Prime', monospace; margin-bottom: 8px;">Output:</div>
                    """)
                    continue

            # Check for Lists
            if r"\begin{itemize}" in line:
                html_out.append("<ul style='margin: 8px 0 8px 24px; padding-left: 0;'>")
                continue
            if r"\end{itemize}" in line:
                html_out.append("</ul>")
                continue
            if r"\begin{enumerate}" in line or r"\begin{parts}" in line:
                html_out.append("<ol style='margin: 8px 0 8px 24px; padding-left: 0;'>")
                continue
            if r"\end{enumerate}" in line or r"\end{parts}" in line:
                html_out.append("</ol>")
                continue

            # Process inline formatting & Marks
            marks_html = ""
            marks_m = re.search(r"\\Marks\{([^}]+)\}", line)
            if marks_m:
                marks_html = f"<span class='marks-bracket'>[{marks_m.group(1)}]</span>"
                line = re.sub(r"\\Marks\{[^}]+\}", "", line)

            line = re.sub(r"\\code\{([^}]+)\}", r"<code class='inline-code'>\1</code>", line)
            line = re.sub(r"\\textbf\{([^}]+)\}", r"<strong>\1</strong>", line)
            line = re.sub(r"\\textit\{([^}]+)\}", r"<em>\1</em>", line)
            line = line.replace(r"\_", "_").replace(r"\#", "#").replace(r"\%", "%").replace(r"\&", "&")
            line = re.sub(r"\\[a-zA-Z]+(\[[^\]]*\])?(\{([^}]*)\})?", r"\3", line)

            if line.startswith(r"\item") or line.startswith("item"):
                clean_item = re.sub(r"^\\item\s*", "", line)
                html_out.append(f"<li class='clearfix' style='margin: 4px 0;'>{clean_item} {marks_html}</li>")
            elif line.strip():
                html_out.append(f"<p class='clearfix' style='margin: 6px 0;'>{line} {marks_html}</p>")

        return "\n".join(html_out)
