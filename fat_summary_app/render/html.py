from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from fat_summary_app.models import FatSummary
from fat_summary_app.render.reportlab_pdf import write_reportlab_visual_summary_pdf
from fat_summary_app.render.template_data import build_visual_template_context


def render_visual_summary_html(summary: FatSummary) -> str:
    template_dir = Path(__file__).resolve().parents[1] / "templates"
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
    )
    template = env.get_template("qualitrol_visual_summary.html.j2")
    return template.render(**build_visual_template_context(summary))


def write_visual_summary_pdf(summary: FatSummary, output_path: str | Path) -> None:
    write_reportlab_visual_summary_pdf(summary, output_path)
    return

    html = render_visual_summary_html(summary)
    if _write_chromium_pdf(html, output_path):
        return
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from weasyprint import HTML
    except OSError:
        write_reportlab_visual_summary_pdf(summary, output_path)
        return
    except Exception:
        write_reportlab_visual_summary_pdf(summary, output_path)
        return

    HTML(string=html, base_url=str(Path(__file__).resolve().parents[1])).write_pdf(str(output_path))


def _write_chromium_pdf(html: str, output_path: str | Path) -> bool:
    chrome = _find_chrome()
    if not chrome:
        return False
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as temp:
            temp.write(html)
            temp_path = Path(temp.name)
        with sync_playwright() as play:
            browser = play.chromium.launch(executable_path=str(chrome), headless=True)
            page = browser.new_page(viewport={"width": 1123, "height": 794})
            page.goto(temp_path.resolve().as_uri(), wait_until="load")
            page.pdf(
                path=str(output_path),
                format="A4",
                landscape=True,
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                prefer_css_page_size=True,
            )
            browser.close()
        return True
    except Exception:
        return False
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _find_chrome() -> Path | None:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    return next((path for path in candidates if path.exists()), None)
