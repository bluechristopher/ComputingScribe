"""
EduScribe AI - LaTeX Visual Typesetting & Sheet Renderer
Renders Cambridge Examination LaTeX papers and Mark Schemes using KaTeX in clean HTML,
focusing purely on the technical questions, code listings, decision tables, and marks.
"""

import re
import html
from typing import Dict, Any, List

class LaTeXVisualRenderer:
    @staticmethod
    def render_questions_only_html(latex_source: str, title: str = "Question Paper") -> str:
        """
        Renders purely the examination questions, subtasks, Jupyter cells, pseudocode,
        tables, and marks using KaTeX, omitting document formatting headers/footers.
        """
        # Extract document body
        body_match = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", latex_source, re.DOTALL)
        body_text = body_match.group(1) if body_match else latex_source

        # Strip out document-level header / footer noise & cover page directives
        body_text = re.sub(r"\\begin\{coverpage\}.*?\\end\{coverpage\}", "", body_text, flags=re.DOTALL)
        body_text = re.sub(r"\\thispagestyle\{[^}]+\}", "", body_text)
        body_text = re.sub(r"\\pagestyle\{[^}]+\}", "", body_text)
        body_text = re.sub(r"\\maketitle", "", body_text)

        # Process the clean questions content
        content_html = LaTeXVisualRenderer._process_page_content(body_text)

        html_doc = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
            <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js"></script>
            <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js"
                onload="renderMathInElement(document.body, {{
                    delimiters: [
                        {{left: '$$', right: '$$', display: true}},
                        {{left: '$', right: '$', display: false}},
                        {{left: '\\\\(', right: '\\\\)', display: false}},
                        {{left: '\\\\[', right: '\\\\]', display: true}}
                    ]
                }});"></script>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap');
                
                body {{
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background-color: #ffffff;
                    margin: 0;
                    padding: 24px 32px;
                    color: #0f172a;
                    font-size: 11pt;
                    line-height: 1.6;
                }}
                
                .maintask-title {{
                    font-size: 1.25rem;
                    font-weight: 700;
                    margin-top: 24px;
                    margin-bottom: 10px;
                    color: #1e3a8a;
                    border-bottom: 2px solid #e2e8f0;
                    padding-bottom: 6px;
                }}
                
                .subtask-title {{
                    font-size: 1.05rem;
                    font-weight: 600;
                    margin-top: 16px;
                    margin-bottom: 6px;
                    color: #0f172a;
                }}
                
                .marks-bracket {{
                    float: right;
                    font-weight: 600;
                    color: #2563eb;
                    background: #eff6ff;
                    padding: 2px 8px;
                    border-radius: 4px;
                    border: 1px solid #bfdbfe;
                    margin-left: 12px;
                    font-size: 0.95rem;
                }}
                
                .jupyter-box {{
                    background: #f8fafc;
                    border: 1px solid #cbd5e1;
                    border-left: 4px solid #2563eb;
                    border-radius: 6px;
                    padding: 10px 14px;
                    margin: 12px 0;
                    font-family: 'Fira Code', monospace;
                    font-size: 10pt;
                }}
                
                .jupyter-label {{
                    color: #2563eb;
                    font-weight: bold;
                    margin-bottom: 4px;
                }}
                
                .jupyter-code {{
                    white-space: pre-wrap;
                    color: #0f172a;
                }}
                
                .pseudocode-box {{
                    background: #f8fafc;
                    border: 1px solid #94a3b8;
                    border-radius: 6px;
                    padding: 12px 16px;
                    margin: 14px 0;
                    font-family: 'Fira Code', monospace;
                    font-size: 10pt;
                    line-height: 1.45;
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
                    border: 1px solid #cbd5e1;
                    padding: 8px 12px;
                    text-align: left;
                    vertical-align: top;
                }}
                
                .exam-table th {{
                    background-color: #f1f5f9;
                    font-weight: 600;
                    color: #1e293b;
                }}
                
                code, .inline-code {{
                    font-family: 'Fira Code', monospace;
                    background: #f1f5f9;
                    color: #1e3a8a;
                    padding: 2px 5px;
                    border-radius: 4px;
                    font-size: 9.5pt;
                    border: 1px solid #e2e8f0;
                }}
                
                ul, ol {{
                    margin: 8px 0 8px 24px;
                    padding-left: 0;
                }}
                
                li {{
                    margin: 4px 0;
                }}
                
                .clearfix::after {{
                    content: "";
                    clear: both;
                    display: table;
                }}
            </style>
        </head>
        <body>
            {content_html}
        </body>
        </html>
        """
        return html_doc

    @staticmethod
    def render_to_html(latex_source: str, title: str = "Examination Paper") -> str:
        """Alias for backward compatibility, renders clean questions."""
        return LaTeXVisualRenderer.render_questions_only_html(latex_source, title)

    @staticmethod
    def _process_page_content(tex_chunk: str) -> str:
        """Processes LaTeX commands inside a chunk into clean semantic HTML."""
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
            if line.startswith(r"\setcounter") or line.startswith(r"\TurnOver") or line.startswith(r"\NoTurnOver") or line.startswith(r"\newpage"):
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
                    <div style="margin-left: 75px; font-family: 'Fira Code', monospace; margin-bottom: 8px; font-size: 9pt; color: #64748b;">Output:</div>
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
