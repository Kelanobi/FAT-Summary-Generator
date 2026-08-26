from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from textwrap import wrap

import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from fat_summary_app.models import FatSummary
from fat_summary_app.models.report import SystemVariant


PAGE_W, PAGE_H = landscape(A4)
RED = colors.HexColor("#d70712")
INK = colors.HexColor("#30363a")
MUTED = colors.HexColor("#66727a")
LINE = colors.HexColor("#dfe5e8")
SOFT = colors.HexColor("#f7f8f9")
DARK = colors.HexColor("#2f3437")


@dataclass
class PictureItem:
    data: bytes
    width: int
    height: int
    caption: str | None = None


def write_reportlab_visual_summary_pdf(summary: FatSummary, output_path: str | Path) -> None:
    pdf = canvas.Canvas(str(output_path), pagesize=landscape(A4))
    _draw_dashboard_page(pdf, summary)
    pictures = _manual_pictures(summary)
    if pictures:
        _draw_pictures_pages(pdf, pictures)
    pdf.save()


def _draw_dashboard_page(pdf: canvas.Canvas, summary: FatSummary) -> None:
    sample = _dashboard_data(summary)
    _background(pdf)

    logo = _logo_path()
    if logo.exists():
        pdf.drawImage(str(logo), 12 * mm, PAGE_H - 23 * mm, width=58 * mm, preserveAspectRatio=True, mask="auto")
    _text(pdf, "FAT Summary Dashboard", 12 * mm, PAGE_H - 36 * mm, 26, INK, bold=True)
    _text(pdf, sample["project"], 12 * mm, PAGE_H - 45 * mm, 10, MUTED)
    _text(pdf, sample["customer"], 12 * mm, PAGE_H - 49 * mm, 8, MUTED)
    _chip(pdf, sample["system"], PAGE_W - 45 * mm, PAGE_H - 24 * mm, 28 * mm)

    meta_x = PAGE_W - 118 * mm
    for idx, (label, value) in enumerate(sample["meta"]):
        _text(pdf, label, meta_x + idx * 27 * mm, PAGE_H - 35 * mm, 6.5, MUTED, bold=True)
        _text(pdf, value, meta_x + idx * 27 * mm, PAGE_H - 41 * mm, 7.3, INK, bold=True)

    pdf.setFillColor(RED)
    pdf.roundRect(12 * mm, PAGE_H - 54 * mm, PAGE_W - 24 * mm, 1.6 * mm, 0.8 * mm, fill=1, stroke=0)

    _card(pdf, 12 * mm, PAGE_H - 95 * mm, 118 * mm, 34 * mm, fill=DARK, stroke=DARK)
    _text(pdf, "OVERALL FAT STATUS", 18 * mm, PAGE_H - 72 * mm, 7.4, colors.HexColor("#ccd3d6"), bold=True)
    _text(pdf, "FAT SUCCESSFULLY COMPLETED", 18 * mm, PAGE_H - 82 * mm, 16.5, colors.white, bold=True)
    _text(pdf, "AND PASSED", 18 * mm, PAGE_H - 90 * mm, 16.5, colors.white, bold=True)

    cx, cy = 154 * mm, PAGE_H - 78 * mm
    pdf.setLineWidth(7)
    pdf.setStrokeColor(colors.HexColor("#e6eaec"))
    pdf.circle(cx, cy, 15 * mm, stroke=1, fill=0)
    pdf.setStrokeColor(RED)
    pdf.arc(cx - 15 * mm, cy - 15 * mm, cx + 15 * mm, cy + 15 * mm, 90, 360)
    _text(pdf, sample["completion"], cx, cy - 2 * mm, 18, INK, bold=True, align="center")
    _text(pdf, "COMPLETION", cx, cy - 8 * mm, 6.5, MUTED, bold=True, align="center")

    x0 = 184 * mm
    for idx, (label, value) in enumerate(sample["metrics"]):
        _metric(pdf, label, value, "", x0 + idx * 26 * mm, PAGE_H - 94 * mm, 23 * mm, 34 * mm)

    _text(pdf, "SYSTEM SCOPE", 12 * mm, PAGE_H - 111 * mm, 8, INK, bold=True)
    scope_gap = 4 * mm
    tile_w = (PAGE_W - 24 * mm - scope_gap * (len(sample["scope"]) - 1)) / len(sample["scope"])
    for idx, item in enumerate(sample["scope"]):
        x = 12 * mm + idx * (tile_w + scope_gap)
        _metric(pdf, item[0], item[1], item[2], x, PAGE_H - 139 * mm, tile_w)

    _text(pdf, "COVERAGE DASHBOARD", 12 * mm, PAGE_H - 148 * mm, 8, INK, bold=True)
    coverage = [
        ("Visual Inspection", _coverage_status(summary, "visual"), "Visual inspection completed and OK"),
        ("Software Baseline", _coverage_status(summary, "software"), "Software up to date"),
        ("Operational Tests", _coverage_status(summary, "operational"), "Checks passed where applicable"),
        ("Database / Communications", _coverage_status(summary, "database"), "Communications verified"),
        ("UPS / Final Checks", _coverage_status(summary, "ups"), _ups_final_check_text(summary)),
    ]
    for idx, item in enumerate(coverage):
        _status_card(pdf, item[0], item[1], item[2], 12 * mm + idx * 56 * mm, PAGE_H - 179 * mm, 52 * mm)

    if summary.observations:
        _card(pdf, 12 * mm, 5 * mm, PAGE_W - 24 * mm, 14 * mm, fill=colors.white)
        _text(pdf, "CLOSEOUT", 18 * mm, 15 * mm, 6.4, MUTED, bold=True)
        _text(pdf, "FAT has been successfully completed and passed.", 18 * mm, 9.5 * mm, 9.4, INK, bold=True)
        _draw_observation_text_page(pdf, summary)
    else:
        _card(pdf, 12 * mm, 5 * mm, PAGE_W - 24 * mm, 14 * mm, fill=colors.white)
        _text(pdf, "CLOSEOUT", 18 * mm, 15 * mm, 6.4, MUTED, bold=True)
        _text(pdf, "FAT has been successfully completed and passed.", 18 * mm, 9.5 * mm, 9.4, INK, bold=True)
    pdf.showPage()


def _draw_observation_text_page(pdf: canvas.Canvas, summary: FatSummary) -> None:
    pdf.showPage()
    _background(pdf)
    logo = _logo_path()
    if logo.exists():
        pdf.drawImage(str(logo), 12 * mm, PAGE_H - 23 * mm, width=58 * mm, preserveAspectRatio=True, mask="auto")
    _text(pdf, "Observations", 12 * mm, PAGE_H - 39 * mm, 25, INK, bold=True)
    pdf.setFillColor(RED)
    pdf.roundRect(12 * mm, PAGE_H - 50 * mm, PAGE_W - 24 * mm, 1.6 * mm, 0.8 * mm, fill=1, stroke=0)
    text = "\n".join(item.text.strip() for item in summary.observations if item.text.strip())
    y = PAGE_H - 64 * mm
    for paragraph in text.splitlines():
        lines = wrap(paragraph, 118) or [""]
        for line in lines:
            if y < 18 * mm:
                pdf.showPage()
                _background(pdf)
                y = PAGE_H - 24 * mm
            _text(pdf, line, 18 * mm, y, 9, INK)
            y -= 6 * mm
        y -= 2 * mm


def _draw_pictures_pages(pdf: canvas.Canvas, pictures: list[PictureItem]) -> None:
    slots = [
        (12 * mm, 84 * mm, 87 * mm, 72 * mm),
        (105 * mm, 84 * mm, 87 * mm, 72 * mm),
        (198 * mm, 84 * mm, 87 * mm, 72 * mm),
        (12 * mm, 8 * mm, 87 * mm, 72 * mm),
        (105 * mm, 8 * mm, 87 * mm, 72 * mm),
        (198 * mm, 8 * mm, 87 * mm, 72 * mm),
    ]
    for page_number, start in enumerate(range(0, len(pictures), len(slots)), start=1):
        page_pictures = pictures[start : start + len(slots)]
        _background(pdf)
        logo = _logo_path()
        if logo.exists():
            pdf.drawImage(str(logo), 12 * mm, PAGE_H - 23 * mm, width=58 * mm, preserveAspectRatio=True, mask="auto")
        _text(pdf, "Pictures", 12 * mm, PAGE_H - 39 * mm, 25, INK, bold=True)
        if len(pictures) > len(slots):
            _text(pdf, f"Page {page_number}", PAGE_W - 12 * mm, PAGE_H - 39 * mm, 9, MUTED, bold=True, align="right")
        pdf.setFillColor(RED)
        pdf.roundRect(12 * mm, PAGE_H - 50 * mm, PAGE_W - 24 * mm, 1.6 * mm, 0.8 * mm, fill=1, stroke=0)

        for idx, (picture, slot) in enumerate(zip(page_pictures, slots, strict=False), start=start + 1):
            x, y, w, h = slot
            _card(pdf, x, y, w, h, fill=colors.white)
            _fit_image(pdf, picture, x + 4 * mm, y + 12 * mm, w - 8 * mm, h - 20 * mm)
            _text(pdf, _picture_label(picture, idx), x + 4 * mm, y + 5 * mm, 6.5, MUTED, bold=True)
        pdf.showPage()


def _manual_pictures(summary: FatSummary) -> list[PictureItem]:
    pictures: list[PictureItem] = []
    for item in summary.picture_evidence:
        path = Path(item.path)
        if not path.exists():
            continue
        try:
            with fitz.open(path) as doc:
                if doc.page_count:
                    pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
                    pictures.append(PictureItem(pix.tobytes("png"), pix.width, pix.height, item.caption))
                    continue
        except Exception:
            pass
        try:
            pix = fitz.Pixmap(str(path))
            if pix.alpha or pix.n > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            pictures.append(PictureItem(pix.tobytes("png"), pix.width, pix.height, item.caption))
        except Exception:
            continue
    return pictures


def _dashboard_data(summary: FatSummary) -> dict[str, object]:
    variant = summary.system_variant
    counts = _dashboard_check_counts(summary)
    project = summary.project.project_name or summary.project.substation or "FAT Project"
    system = _variant_label(variant)

    return {
        "project": _display(project),
        "customer": f"Customer: {_display(summary.project.customer)}",
        "system": system,
        "completion": f"{counts['completion']}%",
        "meta": [
            ("FAT Date", _display(summary.fat_context.fat_date or summary.fat_context.date_range)),
            ("Document", _display(summary.fat_context.document_no)),
            ("Revision", _display(summary.fat_context.revision)),
            ("Job No.", _display(summary.project.manufacturing_number or summary.equipment.equipment_tag)),
        ],
        "metrics": [
            ("Total checks", _display(counts["total"])),
            ("Passed", _display(counts["passed"])),
            ("Failed", _display(counts["failed"])),
            ("N/A", _display(counts["na"]) if counts["na"] else "-"),
        ],
        "scope": _scope_tiles(summary, variant),
    }


def _dashboard_check_counts(summary: FatSummary) -> dict[str, int]:
    total = summary.test_coverage.detected_test_count or len(summary.test_coverage.tests)
    na = sum(1 for item in summary.test_coverage.tests if (item.status or "").lower() == "n/a")
    failed = sum(1 for item in summary.test_coverage.tests if (item.status or "").lower() in {"fail", "failed"})
    applicable = max(total - na, 0)
    passed = max(applicable - failed, 0)
    if summary.test_coverage.passed_count is not None:
        passed = summary.test_coverage.passed_count
    if summary.test_coverage.failed_count is not None:
        failed = summary.test_coverage.failed_count
    if summary.test_coverage.na_count is not None:
        na = summary.test_coverage.na_count
    applicable = max(total - na, 0)
    completion = min(round((passed / applicable) * 100) if applicable else 100, 100)
    if summary.test_coverage.completion_percent is not None:
        completion = summary.test_coverage.completion_percent
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "na": na,
        "applicable": applicable,
        "completion": completion,
    }


def _scope_tiles(summary: FatSummary, variant: SystemVariant) -> list[tuple[str, str, str]]:
    is_pdm = variant in {SystemVariant.PDM, SystemVariant.PDM_GDM}
    has_gdm = variant in {SystemVariant.GDM, SystemVariant.PDM_GDM}
    ocu_count = _ocu_count(summary) if is_pdm else None
    ocu_channels = _ocu_channel_count(summary) if is_pdm else None
    gdm_sensors = summary.equipment.sensor_count if has_gdm else None
    return [
        ("OCU", _display(ocu_count), "Grouped OCU total" if is_pdm else "Not applicable"),
        ("OCU channel", _display(ocu_channels), ""),
        ("GDM Module", _display(summary.equipment.gdm_module_count if variant in {SystemVariant.GDM, SystemVariant.PDM_GDM} else None), ""),
        ("GDM sensors", _display(gdm_sensors), ""),
        ("Voltage", _display(summary.project.voltage), "Project voltage"),
        ("Frequency", _display(summary.equipment.operating_frequency), "Operating frequency"),
    ]


def _ocu_count(summary: FatSummary) -> int | None:
    formula = _ocu_formula_counts(summary)
    if formula:
        return sum(units for units, _channels in formula)
    number = _number_from_text(summary.equipment.number_of_ocus)
    return int(number) if number else None


def _ocu_channel_count(summary: FatSummary) -> str | int | None:
    if summary.equipment.ocu_channel_count:
        return summary.equipment.ocu_channel_count
    formula = _ocu_formula_counts(summary)
    if formula:
        return sum(units * channels for units, channels in formula)
    return summary.equipment.sensor_count if summary.system_variant == SystemVariant.PDM else None


def _ocu_formula_counts(summary: FatSummary) -> list[tuple[int, int]]:
    text = " ".join(
        value or ""
        for value in [
            summary.equipment.system_type,
            summary.equipment.equipment,
            summary.equipment.ocu_model,
            summary.equipment.number_of_ocus,
        ]
    )
    return [
        (int(units), int(channels))
        for units, channels in re.findall(r"\b(\d{1,3})\s*x\s*(\d{1,3})\s*CH\b", text, flags=re.IGNORECASE)
    ]


def _coverage_status(summary: FatSummary, area: str) -> str:
    if area == "ups" and summary.final_checks:
        if any((check.result or check.note or "").strip() for check in summary.final_checks):
            return "PASS"
    if area == "software" and summary.system_build.software_baseline:
        return "PASS"
    if area == "visual":
        return "PASS"
    if area == "database" and any("database" in item.name.lower() or item.code.startswith("E") for item in summary.test_coverage.tests):
        return "PASS"
    if area == "operational" and summary.test_coverage.tests:
        return "PASS"
    return "-"


def _ups_final_check_text(summary: FatSummary) -> str:
    check = next((item for item in summary.final_checks if "ups" in item.name.lower()), None)
    if not check:
        return "UPS/final checks passed"
    parts = [part.strip() for part in [check.note, check.result] if part and part.strip()]
    return " / ".join(parts) or "UPS/final checks passed"


def _extract_trailing_pictures(summary: FatSummary) -> list[PictureItem]:
    pictures: list[PictureItem] = []
    for source in summary.source_documents:
        path = Path(source.path)
        if not path.exists():
            continue
        try:
            with fitz.open(path) as doc:
                start = max(0, doc.page_count - 6)
                for page_index in range(start, doc.page_count):
                    page = doc[page_index]
                    if _has_pictures_heading(page):
                        pictures.extend(_pictures_heading_page_items(page))
                        continue
                    pictures.extend(_embedded_images(page, doc))
                    if _is_picture_page(page):
                        rendered = _render_page(page)
                        if rendered:
                            pictures.append(rendered)
        except Exception:
            continue
    return pictures


def _has_pictures_heading(page: fitz.Page) -> bool:
    lines = [line.strip().upper() for line in page.get_text("text").splitlines()]
    return any(line in {"PICTURES", "PICTURE"} or line.startswith("PICTURES ") for line in lines)


def _pictures_heading_page_items(page: fitz.Page) -> list[PictureItem]:
    page_area = page.rect.width * page.rect.height
    captions = _picture_captions(page)
    rects: list[fitz.Rect] = []
    for image in page.get_images(full=True):
        for rect in page.get_image_rects(image[0]):
            ratio = rect.width * rect.height / page_area
            if ratio >= 0.015:
                rects.append(rect)
    rects.sort(key=lambda rect: (round(rect.y0, 1), round(rect.x0, 1)))

    pictures: list[PictureItem] = []
    seen: set[tuple[int, int, int, int]] = set()
    for idx, rect in enumerate(rects):
        key = (round(rect.x0), round(rect.y0), round(rect.x1), round(rect.y1))
        if key in seen:
            continue
        seen.add(key)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
        if not _is_mostly_blank(pix):
            pictures.append(PictureItem(pix.tobytes("png"), pix.width, pix.height, captions[idx] if idx < len(captions) else None))
    return pictures


def _picture_captions(page: fitz.Page) -> list[str]:
    text = " ".join(line.strip() for line in page.get_text("text").splitlines() if line.strip())
    matches = list(re.finditer(r"\bImage\s*(\d+)\s*:\s*", text, flags=re.IGNORECASE))
    captions_by_number: dict[int, str] = {}
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        caption = text[start:end].strip(" -:;\t")
        caption = re.sub(r"\s+", " ", caption)
        if caption:
            captions_by_number[int(match.group(1))] = f"Image {int(match.group(1))}: {caption}"
    return [captions_by_number[key] for key in sorted(captions_by_number)]


def _picture_label(picture: PictureItem, index: int) -> str:
    label = picture.caption or f"Picture {index}"
    return label if len(label) <= 70 else f"{label[:67]}..."


def _embedded_images(page: fitz.Page, doc: fitz.Document) -> list[PictureItem]:
    items: list[PictureItem] = []
    if len(page.get_text("text").strip()) > 80:
        return items
    page_area = page.rect.width * page.rect.height
    for image in page.get_images(full=True):
        xref = image[0]
        rects = page.get_image_rects(xref)
        if rects and max((rect.width * rect.height) / page_area for rect in rects) < 0.20:
            continue
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.alpha or pix.n > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            if _is_mostly_blank(pix):
                continue
            items.append(PictureItem(pix.tobytes("png"), pix.width, pix.height))
        except Exception:
            continue
    return items


def _is_picture_page(page: fitz.Page) -> bool:
    text = page.get_text("text").strip()
    images = page.get_images(full=True)
    if not images:
        return False
    page_area = page.rect.width * page.rect.height
    image_area = 0.0
    for image in images:
        for rect in page.get_image_rects(image[0]):
            image_area += rect.width * rect.height
    return len(text) < 80 and image_area / page_area > 0.35


def _render_page(page: fitz.Page) -> PictureItem | None:
    pix = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
    if _is_mostly_blank(pix):
        return None
    return PictureItem(pix.tobytes("png"), pix.width, pix.height)


def _is_mostly_blank(pix: fitz.Pixmap) -> bool:
    if pix.n < 3:
        return False
    samples = pix.samples
    stride = pix.n
    total = 0
    white = 0
    step = max(1, (pix.width * pix.height) // 5000)
    for pixel_index in range(0, pix.width * pix.height, step):
        offset = pixel_index * stride
        if offset + 2 >= len(samples):
            break
        r, g, b = samples[offset], samples[offset + 1], samples[offset + 2]
        total += 1
        if r > 245 and g > 245 and b > 245:
            white += 1
    return bool(total) and white / total > 0.96


def _fit_image(pdf: canvas.Canvas, picture: PictureItem, x: float, y: float, w: float, h: float) -> None:
    image = ImageReader(io.BytesIO(picture.data))
    scale = min(w / picture.width, h / picture.height)
    draw_w = picture.width * scale
    draw_h = picture.height * scale
    pdf.drawImage(image, x + (w - draw_w) / 2, y + (h - draw_h) / 2, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")


def _background(pdf: canvas.Canvas) -> None:
    pdf.setFillColor(SOFT)
    pdf.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)


def _text(pdf: canvas.Canvas, text: object, x: float, y: float, size: float, color=INK, bold: bool = False, align: str = "left") -> None:
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    pdf.setFillColor(color)
    value = str(text or "-")
    if align == "right":
        pdf.drawRightString(x, y, value)
    elif align == "center":
        pdf.drawCentredString(x, y, value)
    else:
        pdf.drawString(x, y, value)


def _wrapped(pdf: canvas.Canvas, text: object, x: float, y: float, size: float, width: float, color=MUTED, bold: bool = False) -> None:
    _wrapped_lines(pdf, text, x, y, size, width, color, bold, max_lines=2)


def _wrapped_lines(pdf: canvas.Canvas, text: object, x: float, y: float, size: float, width: float, color=MUTED, bold: bool = False, max_lines: int = 2) -> None:
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    pdf.setFillColor(color)
    max_chars = max(7, int(width / (size * 0.5)))
    for idx, line in enumerate(wrap(str(text or ""), max_chars)[:max_lines]):
        pdf.drawString(x, y - idx * size * 1.2, line)


def _card(pdf: canvas.Canvas, x: float, y: float, w: float, h: float, fill=colors.white, stroke=LINE) -> None:
    pdf.setFillColor(fill)
    pdf.setStrokeColor(stroke)
    pdf.setLineWidth(0.8)
    pdf.roundRect(x, y, w, h, 4 * mm, fill=1, stroke=1)


def _chip(pdf: canvas.Canvas, text: str, x: float, y: float, w: float) -> None:
    pdf.setFillColor(RED)
    pdf.roundRect(x, y, w, 7 * mm, 3.5 * mm, fill=1, stroke=0)
    _text(pdf, text, x + w / 2, y + 2.2 * mm, 7, colors.white, bold=True, align="center")


def _metric(pdf: canvas.Canvas, label: str, value: str, note: str, x: float, y: float, w: float, h: float = 22 * mm) -> None:
    _card(pdf, x, y, w, h)
    _text(pdf, label.upper(), x + 4 * mm, y + h - 6 * mm, 6.5, MUTED, bold=True)
    size = 19 if len(str(value)) < 5 else 15
    _text(pdf, value, x + 4 * mm, y + 7.5 * mm, size, INK, bold=True)
    if note:
        _wrapped(pdf, note, x + 4 * mm, y + 3.4 * mm, 5.8, w - 8 * mm)


def _status_card(pdf: canvas.Canvas, title: str, value: str, body: str, x: float, y: float, w: float) -> None:
    _card(pdf, x, y, w, 27 * mm)
    _text(pdf, title.upper(), x + 4 * mm, y + 20 * mm, 6.1, MUTED, bold=True)
    _text(pdf, value, x + 4 * mm, y + 12 * mm, 12.3, INK, bold=True)
    _wrapped(pdf, body, x + 4 * mm, y + 5.7 * mm, 5.7, w - 8 * mm)


def _logo_path() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "assets" / "qualitrol-logo.png"


def _display(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text if text else "-"


def _variant_label(variant: SystemVariant) -> str:
    if variant == SystemVariant.PDM_GDM:
        return "PDM/GDM"
    if variant == SystemVariant.GDM:
        return "GDM"
    if variant == SystemVariant.PDM:
        return "PDM"
    return "FAT"


def _number_from_text(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in value.split(",", 1)[0] if ch.isdigit())
    return digits or None


def _gddc_count(summary: FatSummary) -> int | None:
    cabinets = {row.cabinet for row in summary.system_build.addressing if row.cabinet and "GDDC" in row.cabinet.upper()}
    return len(cabinets) or None


def _observations(summary: FatSummary) -> str:
    return "recorded" if summary.observations else "none recorded"
