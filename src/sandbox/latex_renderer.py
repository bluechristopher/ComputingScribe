"""
EduScribe AI - LaTeX Visual Typesetting & Sheet Renderer
Renders Cambridge Examination LaTeX papers and Mark Schemes using KaTeX in clean,
publication-grade HTML with full support for tables, Jupyter code cells, test cases,
pseudocode, mathematics, and right-aligned mark brackets.
"""

import re
import html
from typing import Dict, Any, List, Optional

class LaTeXVisualRenderer:
    @staticmethod
    def render_questions_only_html(
        latex_source: str,
        title: str = "Question Paper",
        image_data_urls: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Renders examination questions, subtasks, Jupyter cells, pseudocode,
        tables, and marks using KaTeX, omitting document-level cover/header boilerplate.
        """
        if not latex_source:
            return "<div style='padding: 20px; color: #64748b;'>No content to preview.</div>"

        # Extract document body if full LaTeX document
        body_match = re.search(r"\\begin\{document\}(.*?)\\end\{document\}", latex_source, re.DOTALL)
        body_text = body_match.group(1) if body_match else latex_source

        # Strip out document-level header / footer noise & cover page directives
        body_text = re.sub(r"\\begin\{coverpage\}.*?\\end\{coverpage\}", "", body_text, flags=re.DOTALL)
        body_text = re.sub(r"\\thispagestyle\{[^}]*\}", "", body_text)
        body_text = re.sub(r"\\pagestyle\{[^}]*\}", "", body_text)
        body_text = re.sub(r"\\maketitle", "", body_text)
        body_text = re.sub(r"\\setcounter\{[^}]*\}\{[^}]*\}", "", body_text)

        # Process the clean questions content
        content_html = LaTeXVisualRenderer._process_latex_document(body_text, image_data_urls or {})

        html_doc = f"""<!DOCTYPE html>
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
            ],
            throwOnError: false
        }});"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Fira+Code:wght@400;500;600&display=swap');
        
        * {{
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #ffffff;
            margin: 0;
            padding: 24px 36px;
            color: #0f172a;
            font-size: 11pt;
            line-height: 1.65;
        }}
        
        .paper-header {{
            border-bottom: 3px solid #1e3a8a;
            padding-bottom: 12px;
            margin-bottom: 24px;
        }}
        
        .paper-title {{
            font-size: 1.4rem;
            font-weight: 800;
            color: #0f172a;
            letter-spacing: -0.3px;
        }}
        
        .maintask-box {{
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-left: 5px solid #2563eb;
            border-radius: 8px;
            padding: 12px 18px;
            margin-top: 28px;
            margin-bottom: 14px;
        }}
        
        .maintask-title {{
            font-size: 1.25rem;
            font-weight: 800;
            color: #1e3a8a;
            margin: 0;
        }}
        
        .subtask-title {{
            font-size: 1.05rem;
            font-weight: 700;
            color: #0f172a;
            margin-top: 20px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
        }}
        
        .subtask-badge {{
            background: #dbeafe;
            color: #1e40af;
            font-size: 0.85rem;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 4px;
            margin-right: 8px;
        }}
        
        .marks-bracket {{
            float: right;
            font-weight: 700;
            color: #ffffff !important;
            background: linear-gradient(145deg, #1e293b, #0f172a) !important;
            padding: 2px 9px;
            border-radius: 6px;
            border: 1px solid #475569;
            margin-left: 14px;
            font-size: 0.92rem;
            letter-spacing: 0.2px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
        }}
        
        .inline-code, code {{
            font-family: 'Courier New', 'Fira Code', 'Lucida Console', monospace !important;
            background-color: #f1f5f9;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.92em;
            font-weight: 600;
        }}
        
        .jupyter-intro-block {{
            margin: 14px 0 18px 0;
            font-size: 10pt;
            line-height: 1.55;
            color: #1e293b;
        }}
        
        .jupyter-cell-aligned {{
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin: 10px 0 4px 0;
        }}
        
        .jupyter-in-tag {{
            font-family: 'Courier New', monospace;
            font-size: 10pt;
            font-weight: 700;
            color: #0f172a;
            white-space: nowrap;
            padding-top: 4px;
        }}
        
        .jupyter-grey-frame {{
            background: #ebeef2;
            border: 1px solid #334155;
            border-radius: 3px;
            padding: 7px 14px;
            flex: 1;
            max-width: 550px;
            font-family: 'Courier New', monospace;
            font-style: italic;
            color: #0f172a;
            line-height: 1.45;
        }}
        
        .jupyter-output-tag {{
            font-family: 'Courier New', monospace;
            font-size: 10pt;
            color: #0f172a;
            margin-left: 64px;
            margin-top: 4px;
            margin-bottom: 12px;
        }}

        .blank-page-divider {{
            text-align: center;
            margin: 4px 0 10px 0;
            padding: 0;
            border-top: 1px dashed #cbd5e1;
        }}

        .blank-page-text {{
            font-size: 1.15rem;
            font-weight: 800;
            letter-spacing: 2px;
            color: #0f172a;
            margin-top: 4px;
            margin-bottom: 20px;
        }}
        
        .pseudocode-box {{
            background: #f8fafc;
            border: 1px solid #94a3b8;
            border-radius: 6px;
            padding: 14px 18px;
            margin: 16px 0;
            font-family: 'Fira Code', monospace;
            font-size: 10pt;
            line-height: 1.5;
        }}
        
        .pseudo-line {{
            display: flex;
            align-items: flex-start;
        }}
        
        .line-num {{
            width: 36px;
            color: #64748b;
            user-select: none;
            font-weight: 700;
            flex-shrink: 0;
        }}
        
        .exam-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
            font-size: 10pt;
            background: #ffffff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        
        .exam-table th, .exam-table td {{
            border: 1px solid #cbd5e1;
            padding: 10px 14px;
            text-align: left;
            vertical-align: top;
        }}
        
        .exam-table th {{
            background-color: #f1f5f9;
            font-weight: 700;
            color: #0f172a;
            border-bottom: 2px solid #94a3b8;
        }}
        
        .testcases-box {{
            background: #fefce8;
            border: 1px solid #fef08a;
            border-left: 4px solid #eab308;
            border-radius: 6px;
            padding: 10px 14px;
            margin: 12px 0;
            font-size: 10pt;
        }}
        
        .testcases-title {{
            font-weight: 700;
            color: #854d0e;
            margin-bottom: 6px;
            font-size: 0.9rem;
        }}
        
        code, .inline-code {{
            font-family: 'Fira Code', monospace;
            background: #f1f5f9;
            color: #1e3a8a;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 9.5pt;
            border: 1px solid #e2e8f0;
            font-weight: 500;
        }}
        
        .questions-list {{
            list-style-type: decimal;
            margin: 18px 0 18px 24px;
            padding-left: 0;
        }}
        
        .questions-list > li {{
            margin: 22px 0 16px 0;
            font-weight: 700;
            color: #0f172a;
            font-size: 1.08rem;
        }}
        
        .questions-list > li > * {{
            font-weight: 400;
            font-size: 11pt;
        }}
        
        .parts-list {{
            list-style-type: lower-alpha;
            margin: 10px 0 10px 24px;
            padding-left: 0;
        }}
        
        .parts-list > li {{
            margin: 10px 0;
            font-weight: 400;
            color: #0f172a;
        }}
        
        .subparts-list {{
            list-style-type: lower-roman;
            margin: 8px 0 8px 24px;
            padding-left: 0;
        }}
        
        .subparts-list > li {{
            margin: 8px 0;
            font-weight: 400;
            color: #1e293b;
        }}
        
        .tightitemize {{
            list-style-type: disc;
            margin: 8px 0 8px 20px;
            padding-left: 0;
        }}
        
        .tightitemize > li {{
            margin: 4px 0;
        }}
        
        ul, ol {{
            margin: 8px 0 8px 24px;
            padding-left: 0;
        }}
        
        li {{
            margin: 6px 0;
        }}
        
        p {{
            margin: 8px 0;
        }}
        
        .section-separator {{
            border-top: 1px dashed #cbd5e1;
            margin: 28px 0;
        }}
        
        .clearfix::after {{
            content: "";
            clear: both;
            display: table;
        }}

        .exam-image {{
            display: block;
            margin: 16px auto;
            max-width: 100%;
            height: auto;
        }}
    </style>
</head>
<body>
    {content_html}
</body>
</html>"""
        return html_doc

    @staticmethod
    def _process_latex_document(tex_text: str, image_data_urls: Dict[str, str]) -> str:
        """Robust LaTeX document parser converting blocks into semantic HTML."""
        # 1. Handle Multiline Jupyter Cells first
        def replace_jupyter(match):
            in_num = match.group(1)
            code_content = match.group(2).replace(r"\\", "\n")
            return f"""
<div class="jupyter-box">
    <div class="jupyter-label">In [{in_num}]:</div>
    <div class="jupyter-code">{html.escape(code_content.strip())}</div>
</div>
<div class="jupyter-output-label">Output:</div>
"""
        tex_text = re.sub(r"\\jupytercell\{([^}]+)\}\{([^}]+)\}", replace_jupyter, tex_text, flags=re.DOTALL)

        # 2. Handle Tables (\begin{tabular} ... \end{tabular} or \begin{tabularx} ... \end{tabularx})
        def replace_table(match):
            table_body = match.group(1)
            rows = table_body.split(r"\\")
            html_rows = []
            is_header = True
            for r in rows:
                r_clean = r.replace(r"\hline", "").strip()
                if not r_clean:
                    continue
                cols = r_clean.split("&")
                col_tags = []
                for c in cols:
                    cell_content = LaTeXVisualRenderer._clean_inline(c.strip())
                    cell_content = cell_content.replace(r"\begin{itemize}", "<ul style='margin: 4px 0 4px 16px; padding: 0;'>").replace(r"\end{itemize}", "</ul>")
                    cell_content = re.sub(r"\\item\s*", "<li>", cell_content)
                    if is_header:
                        col_tags.append(f"<th>{cell_content}</th>")
                    else:
                        col_tags.append(f"<td>{cell_content}</td>")
                html_rows.append(f"<tr>{''.join(col_tags)}</tr>")
                is_header = False
            return f"<table class='exam-table'>{''.join(html_rows)}</table>"

        tex_text = re.sub(r"\\begin\{(?:tabular|tabularx)\}[^\n]*?\n(.*?)\\end\{(?:tabular|tabularx)\}", replace_table, tex_text, flags=re.DOTALL)

        # 3. Handle Pseudocode Blocks
        def replace_pseudocode(match):
            code_lines = match.group(1).strip().splitlines()
            p_html = ["<div class='pseudocode-box'>"]
            for idx, pl in enumerate(code_lines, start=1):
                escaped_code = html.escape(pl)
                # Highlight keywords
                escaped_code = re.sub(r"\b(FUNCTION|ENDFUNCTION|PROCEDURE|ENDPROCEDURE|IF|THEN|ELSE|ENDIF|WHILE|ENDWHILE|FOR|TO|ENDFOR|RETURN|DECLARE|OUTPUT|INPUT)\b", r"<strong>\1</strong>", escaped_code)
                p_html.append(f"<div class='pseudo-line'><span class='line-num'>{idx:02d}</span><span>{escaped_code}</span></div>")
            p_html.append("</div>")
            return "".join(p_html)

        tex_text = re.sub(r"\\begin\{pseudocode\}(.*?)\\end\{pseudocode\}", replace_pseudocode, tex_text, flags=re.DOTALL)

        # 4. Handle Test Cases Blocks
        def replace_testcases(match):
            content = match.group(1).strip()
            items = re.findall(r"\\item\s*(.*?)(?=\\item|$)", content, re.DOTALL)
            t_html = ["<div class='testcases-box'><div class='testcases-title'>🧪 Test Cases & Verification:</div><ul>"]
            for it in items:
                t_html.append(f"<li>{LaTeXVisualRenderer._clean_inline(it.strip())}</li>")
            t_html.append("</ul></div>")
            return "".join(t_html)

        tex_text = re.sub(r"\\begin\{testcases\}(.*?)\\end\{testcases\}", replace_testcases, tex_text, flags=re.DOTALL)

        # 5. Resolve session images stored as \ExamImage{assets/name.png}{0.65\linewidth}.
        def replace_exam_image(match):
            asset_path = match.group(1).strip()
            width_spec = match.group(2).strip()
            data_url = image_data_urls.get(asset_path) or image_data_urls.get(asset_path.rsplit("/", 1)[-1])
            if not data_url:
                return f"<p><em>Image asset unavailable: {html.escape(asset_path)}</em></p>"
            width_match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\\linewidth", width_spec)
            width_style = f"width: {float(width_match.group(1)) * 100:.1f}%;" if width_match else "width: auto;"
            return f"<img class='exam-image' src='{html.escape(data_url, quote=True)}' style='{width_style}' alt='Exam image'>"

        tex_text = re.sub(r"\\ExamImage\{([^}]+)\}\{([^}]+)\}", replace_exam_image, tex_text)

        # 6. Process remaining text line-by-line
        lines = tex_text.splitlines()
        html_out = []
        in_list = False

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("%"):
                continue
            if line.startswith(r"\TurnOver") or line.startswith(r"\NoTurnOver") or line.startswith(r"\newpage"):
                html_out.append("<div class='section-separator'></div>")
                continue
            if r"\PadToMultipleOfFour" in line:
                html_out.append("<div class='blank-page-divider'><div class='blank-page-text'>BLANK PAGE</div></div>")
                continue

            # Cambridge Practical Macros (Paper 2)
            if r"\maintask{" in line:
                m = re.search(r"\\maintask\{([^}]+)\}", line)
                t_num = m.group(1) if m else "1"
                html_out.append(
                    f"<div class='maintask-box'>"
                    f"<h3 class='maintask-title'>Task {t_num}</h3>"
                    f"<p style='margin: 6px 0 4px 0;'>Name your Jupyter Notebook as:</p>"
                    f"<code class='inline-code'>TASK{t_num}_&lt;your name&gt;_&lt;centre number&gt;_&lt;index number&gt;.ipynb</code>"
                    f"</div>"
                )
                continue

            if r"\tasksubtaskintro{" in line or r"\jupytercell{" in line:
                m = re.search(r"\\(?:tasksubtaskintro|jupytercell)\{([^}]+)\}", line)
                t_num = m.group(1) if m else "1"
                html_out.append(
                    f"<div class='jupyter-intro-block'>"
                    f"<p>For each of the sub-tasks, add a comment statement at the beginning of the code, using the hash symbol '#', to indicate the sub-task the program code belongs to, for example:</p>"
                    f"<div class='jupyter-cell-aligned'>"
                    f"<span class='jupyter-in-tag'>In [1]:</span>"
                    f"<div class='jupyter-grey-frame'>#Task {t_num}.1<br>Program code</div>"
                    f"</div>"
                    f"<div class='jupyter-output-tag'>Output:</div>"
                    f"</div>"
                )
                continue

            if r"\taskfooter{" in line:
                m = re.search(r"\\taskfooter\{([^}]+)\}", line)
                t_num = m.group(1) if m else "1"
                html_out.append(f"<p style='margin: 14px 0 18px 0; font-weight: 500;'>Save your Jupyter Notebook for Task {t_num}.</p>")
                continue

            if r"\subtask{" in line:
                m = re.search(r"\\subtask\{([^}]+)\}", line)
                s_num = m.group(1) if m else "1.1"
                html_out.append(f"<div class='subtask-title'><span class='subtask-badge'>Task {s_num}</span></div>")
                continue

            # Cambridge Theory Environments (Paper 1)
            if r"\begin{questions}" in line:
                html_out.append("<ol class='questions-list'>")
                continue
            if r"\end{questions}" in line:
                html_out.append("</ol>")
                continue
            if r"\begin{parts}" in line:
                html_out.append("<ol class='parts-list' type='a'>")
                continue
            if r"\end{parts}" in line:
                html_out.append("</ol>")
                continue
            if r"\begin{subparts}" in line:
                html_out.append("<ol class='subparts-list' type='i'>")
                continue
            if r"\end{subparts}" in line:
                html_out.append("</ol>")
                continue
            if r"\begin{tightitemize}" in line:
                html_out.append("<ul class='tightitemize'>")
                continue
            if r"\end{tightitemize}" in line:
                html_out.append("</ul>")
                continue

            # Standard Lists
            if r"\begin{itemize}" in line:
                html_out.append("<ul>")
                continue
            if r"\end{itemize}" in line:
                html_out.append("</ul>")
                continue
            if r"\begin{enumerate}" in line:
                html_out.append("<ol>")
                continue
            if r"\end{enumerate}" in line:
                html_out.append("</ol>")
                continue

            # Extract Marks Bracket
            marks_html = ""
            marks_m = re.search(r"\\Marks\{([^}]+)\}", line)
            if marks_m:
                marks_html = f"<span class='marks-bracket'>[{marks_m.group(1)}]</span>"
                line = re.sub(r"\\Marks\{[^}]+\}", "", line)

            # Clean inline formatting
            cleaned_line = LaTeXVisualRenderer._clean_inline(line)

            # If already HTML tag (e.g. table, jupyter box)
            if cleaned_line.startswith("<div") or cleaned_line.startswith("<table"):
                html_out.append(cleaned_line)
            elif cleaned_line.startswith(r"\item") or cleaned_line.startswith("item "):
                item_text = re.sub(r"^\\item\s*", "", cleaned_line)
                html_out.append(f"<li class='clearfix'>{item_text} {marks_html}</li>")
            elif cleaned_line:
                html_out.append(f"<p class='clearfix'>{cleaned_line} {marks_html}</p>")

        return "\n".join(html_out)

    @staticmethod
    def _clean_inline(text: str) -> str:
        """Cleans inline LaTeX commands and backticks into HTML tags while preserving math."""
        # Convert backtick code snippets (e.g. `is_empty`) to styled code tags
        text = re.sub(r"`([^`\n]+)`", r"<code class='inline-code'>\1</code>", text)
        # Convert \code{...} and \texttt{...}
        text = re.sub(r"\\(?:code|texttt)\{([^}]+)\}", r"<code class='inline-code'>\1</code>", text)
        text = re.sub(r"\\(?:verb|lstinline)[\|!+^]([^\|!+^]+)[\|!+^]", r"<code class='inline-code'>\1</code>", text)
        text = re.sub(r"\\textbf\{([^}]+)\}", r"<strong>\1</strong>", text)
        text = re.sub(r"\\textit\{([^}]+)\}", r"<em>\1</em>", text)
        text = text.replace(r"\_", "_").replace(r"\#", "#").replace(r"\%", "%").replace(r"\&", "&")
        return text
