"""Export the conference manuscript from LaTeX to readable Markdown and TXT."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def latex_plain(text: str) -> str:
    replacements = {
        r"{\'a}": "á", r"{\'e}": "é", r"{\'i}": "í", r"{\'o}": "ó",
        r"{\'u}": "ú", r"{\"a}": "ä", r"{\"o}": "ö", r"{\"u}": "ü",
        r"{\~a}": "ã", r"{\~o}": "õ", r"{\o}": "ø", r"{\O}": "Ø",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.replace("{", "").replace("}", "")


def inline(text: str) -> str:
    text = text.replace(r"\MOALNS{}", "MOALNS").replace(r"\MOALNS", "MOALNS")
    text = re.sub(
        r"\\SIrange\{([^{}]+)\}\{([^{}]+)\}\{\\percent\}",
        lambda match: f"{match.group(1)}–{match.group(2)}%",
        text,
    )
    text = re.sub(r"\\textbf\{([^{}]*)\}", r"**\1**", text)
    text = re.sub(r"\\emph\{([^{}]*)\}", r"*\1*", text)
    text = re.sub(
        r"\\texttt\{([^{}]*)\}",
        lambda match: "`" + match.group(1).replace(r"\_", "_") + "`",
        text,
    )
    text = re.sub(r"\\cite\{([^{}]+)\}", lambda match: f"[{match.group(1)}]", text)
    text = re.sub(
        r"(Table|Figure)~\\ref\{([^{}]+)\}",
        lambda match: f"[{match.group(1)}](#{match.group(2).replace(':', '-')})",
        text,
    )
    text = re.sub(
        r"\\ref\{([^{}]+)\}",
        lambda match: f"[{match.group(1)}](#{match.group(1).replace(':', '-')})",
        text,
    )
    text = text.replace(r"\%", "%").replace(r"\&", "&")
    text = text.replace(r"\textendash", "–").replace("~", " ")
    text = text.replace(r"\,", " ").replace(r"\;", " ")
    return text.strip()


def parse_caption(block: str) -> str:
    match = re.search(r"\\caption\{(.*?)\}\s*\\label", block, flags=re.DOTALL)
    if not match:
        match = re.search(r"\\caption\{(.*?)\}", block, flags=re.DOTALL)
    return inline(re.sub(r"\s+", " ", match.group(1))) if match else ""


def parse_label(block: str) -> str:
    match = re.search(r"\\label\{([^{}]+)\}", block)
    return match.group(1) if match else ""


def clean_table_cell(cell: str) -> str:
    cell = re.sub(r"\\textbf\{([^{}]*)\}", r"**\1**", cell)
    cell = cell.replace(r"\MOALNS{}", "MOALNS")
    cell = cell.replace(r"\pm", "±").replace(r"\times", "×")
    cell = cell.replace(r"\%", "%").replace("$", "")
    cell = re.sub(r"\\text\{([^{}]*)\}", r"\1", cell)
    cell = re.sub(r"\\[A-Za-z]+", "", cell)
    cell = cell.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", cell).strip()


def convert_table(match: re.Match[str]) -> str:
    block = match.group(0)
    caption, label = parse_caption(block), parse_label(block)
    tabular = re.search(
        r"\\begin\{tabular\}\{[^{}]*\}(.*?)\\end\{tabular\}",
        block,
        flags=re.DOTALL,
    )
    if not tabular:
        return ""
    content = re.sub(r"\\(toprule|midrule|bottomrule)", "", tabular.group(1))
    raw_rows = re.split(r"\\\\", content)
    rows = []
    for raw_row in raw_rows:
        raw_row = re.sub(r"%.*", "", raw_row).strip()
        if not raw_row or "&" not in raw_row:
            continue
        rows.append([clean_table_cell(cell) for cell in raw_row.split("&")])
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    anchor = f'<a id="{label.replace(":", "-")}"></a>\n' if label else ""
    lines = [
        anchor + (f"**Table — {caption}**" if caption else "**Table**"),
        "",
        "| " + " | ".join(rows[0]) + " |",
        "|" + "|".join(["---"] * width) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join(lines)


def convert_figure(match: re.Match[str]) -> str:
    block = match.group(0)
    caption, label = parse_caption(block), parse_label(block)
    image = re.search(r"\\includegraphics(?:\[[^\]]*\])?\{([^{}]+)\}", block)
    path = image.group(1) if image else ""
    image_paths = {
        "fig_projection_survival.pdf": "../outputs/broader_paper/objective_conflict/fig_projection_survival.pdf",
        "paired_hv_delta_vs_baseline.pdf": "../outputs/paper/tail_ablation/paired_hv_delta_vs_baseline.pdf",
        "fig_hypervolume_by_instance.pdf": "../outputs/broader_paper/figures/fig_hypervolume_by_instance.pdf",
        "modm_weight_stability.pdf": "../outputs/studies/modm_weight_sensitivity/modm_weight_stability.pdf",
    }
    path = image_paths.get(path, path)
    anchor = f'<a id="{label.replace(":", "-")}"></a>\n' if label else ""
    return f'{anchor}![{caption}]({path})\n\n*Figure — {caption}*'


def convert_enumerate(match: re.Match[str]) -> str:
    content = match.group(1)
    items = re.split(r"\\item\s+", content)[1:]
    lines = []
    for index, item in enumerate(items, 1):
        normalized = re.sub(r"\s+", " ", item)
        lines.append(f"{index}. {inline(normalized)}")
    return "\n".join(lines)


def bibliography_entries(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    entries = []
    for match in re.finditer(r"@\w+\{([^,]+),(.*?)(?=\n\})", source, flags=re.DOTALL):
        key, body = match.group(1), match.group(2)
        fields = {}
        for field in re.finditer(
            r"(\w+)\s*=\s*\{((?:[^{}]|\{[^{}]*\})*)\}",
            body,
            flags=re.DOTALL,
        ):
            fields[field.group(1).lower()] = re.sub(r"\s+", " ", field.group(2)).strip()
        author = latex_plain(fields.get("author", "")).replace(" and ", "; ")
        title = latex_plain(fields.get("title", ""))
        journal = latex_plain(fields.get("journal", ""))
        year = fields.get("year", "")
        volume = fields.get("volume", "")
        number = fields.get("number", "")
        pages = fields.get("pages", "").replace("--", "–")
        doi = fields.get("doi", "")
        venue = journal
        if volume:
            venue += f", {volume}"
        if number:
            venue += f"({number})"
        if pages:
            venue += f", {pages}"
        doi_text = f" https://doi.org/{doi}" if doi else ""
        entries.append(f"- **{key}.** {author} ({year}). {title}. *{venue}*.{doi_text}")
    return "\n".join(entries)


def markdown_from_latex(tex_path: Path, bib_path: Path) -> str:
    source = tex_path.read_text(encoding="utf-8")
    title_match = re.search(r"\\title\{(.*?)\}\s*\\author", source, flags=re.DOTALL)
    title = inline(re.sub(r"\s+", " ", title_match.group(1))) if title_match else "Conference Manuscript"
    body = source.split(r"\begin{document}", 1)[1].split(r"\end{document}", 1)[0]
    body = body.replace(r"\maketitle", f"# {title}")
    body = re.sub(
        r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
        lambda match: "## Abstract\n\n" + inline(re.sub(r"\s+", " ", match.group(1))),
        body,
        flags=re.DOTALL,
    )
    body = re.sub(r"\\begin\{table\}.*?\\end\{table\}", convert_table, body, flags=re.DOTALL)
    body = re.sub(r"\\begin\{figure\}.*?\\end\{figure\}", convert_figure, body, flags=re.DOTALL)
    body = re.sub(
        r"\\begin\{enumerate\}(?:\[[^\]]*\])?(.*?)\\end\{enumerate\}",
        convert_enumerate,
        body,
        flags=re.DOTALL,
    )
    body = re.sub(
        r"\\begin\{equation\}(.*?)\\end\{equation\}",
        lambda match: "$$\n" + match.group(1).strip() + "\n$$",
        body,
        flags=re.DOTALL,
    )
    body = re.sub(
        r"\\begin\{align\}(.*?)\\end\{align\}",
        lambda match: "$$\n\\begin{aligned}\n" + match.group(1).strip() + "\n\\end{aligned}\n$$",
        body,
        flags=re.DOTALL,
    )
    body = re.sub(r"\\section\*\{([^{}]+)\}", r"## \1", body)
    body = re.sub(r"\\section\{([^{}]+)\}", r"## \1", body)
    body = re.sub(r"\\subsection\{([^{}]+)\}", r"### \1", body)
    body = re.sub(r"\\noindent\\textbf\{([^{}]+)\}", r"**\1**", body)
    body = re.sub(r"\\bibliographystyle\{[^{}]+\}", "", body)
    body = re.sub(
        r"\\bibliography\{[^{}]+\}",
        lambda _: "## References\n\n" + bibliography_entries(bib_path),
        body,
    )
    body = body.replace(r"\centering", "").replace(r"\small", "")
    body = inline(body)
    body = re.sub(r"\n[ \t]+\n", "\n\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip() + "\n"


def text_from_markdown(markdown: str) -> str:
    text = re.sub(r'<a id="[^"]+"></a>\n?', "", markdown)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"Figure: \1 [\2]", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("*", "").replace("`", "")
    text = re.sub(r"^\|", "", text, flags=re.MULTILINE)
    text = re.sub(r"\|$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*(?:---\s*\|?\s*)+$", "", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tex", default="paper/main.tex")
    parser.add_argument("--bib", default="paper/references.bib")
    parser.add_argument("--markdown", default="paper/manuscript.md")
    parser.add_argument("--text", default="paper/manuscript.txt")
    args = parser.parse_args()
    markdown = markdown_from_latex(Path(args.tex), Path(args.bib))
    Path(args.markdown).write_text(markdown, encoding="utf-8")
    Path(args.text).write_text(text_from_markdown(markdown), encoding="utf-8")
    print(f"Markdown: {Path(args.markdown).resolve()}")
    print(f"Text: {Path(args.text).resolve()}")


if __name__ == "__main__":
    main()
