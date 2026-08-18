from __future__ import annotations

import html
import zipfile
from pathlib import Path
from textwrap import wrap
from xml.etree import ElementTree

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_to_text_pdf(source: str | Path, output_path: str | Path) -> Path:
    source_path = Path(source)
    output = Path(output_path)
    text = _extract_docx_text(source_path)
    if not text.strip():
        raise ValueError(f"No readable text found in Word document: {source_path.name}")
    _write_text_pdf(text, output, source_path.name)
    return output


def _extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    lines: list[str] = []
    for paragraph in root.iter(f"{WORD_NS}p"):
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{WORD_NS}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{WORD_NS}tab":
                parts.append("\t")
            elif node.tag == f"{WORD_NS}br":
                parts.append("\n")
        line = html.unescape("".join(parts)).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _write_text_pdf(text: str, output: Path, title: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output), pagesize=A4)
    width, height = A4
    y = height - 18 * mm
    pdf.setTitle(title)
    pdf.setFont("Helvetica", 9)
    for raw_line in text.splitlines():
        lines = wrap(raw_line, 105, replace_whitespace=False, drop_whitespace=False) or [""]
        for line in lines:
            if y < 14 * mm:
                pdf.showPage()
                pdf.setFont("Helvetica", 9)
                y = height - 18 * mm
            pdf.drawString(14 * mm, y, line[:220])
            y -= 4.5 * mm
        y -= 1.5 * mm
    pdf.save()
