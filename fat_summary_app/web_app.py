from __future__ import annotations

import cgi
import json
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import fitz

from fat_summary_app.extract import extract_fat_summary
from fat_summary_app.extract.docx import docx_to_text_pdf
from fat_summary_app.models import FatSummary
from fat_summary_app.models.report import Observation, PictureEvidence
from fat_summary_app.render import write_visual_summary_pdf
from fat_summary_app.review import EDITABLE_FIELDS, apply_review_edits, get_editable_values


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "web_static"
WORK_DIR = Path(tempfile.gettempdir()) / "qualitrol_fat_summary_web"
SESSIONS: dict[str, "SessionState"] = {}


class SessionState:
    def __init__(self) -> None:
        self.root = WORK_DIR / uuid.uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)
        self.sources: list[Path] = []
        self.extracted_summary: FatSummary | None = None
        self.current_summary: FatSummary | None = None
        self.preview_path: Path | None = None
        self.output_path: Path | None = None
        self.filename = "Qualitrol_FAT_Summary.pdf"


class AppHandler(BaseHTTPRequestHandler):
    server_version = "QualitrolFATSummary/1.5"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.css":
            self._send_file(STATIC_DIR / "app.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/qualitrol-logo.png":
            self._send_file(STATIC_DIR / "qualitrol-logo.png", "image/png")
            return
        if parsed.path == "/favicon.png":
            self._send_file(STATIC_DIR / "favicon.png", "image/png")
            return
        if parsed.path == "/favicon.ico":
            self._send_file(STATIC_DIR / "favicon.ico", "image/x-icon")
            return
        if parsed.path == "/file":
            query = parse_qs(parsed.query)
            session = self._session(query.get("session", [""])[0])
            kind = query.get("kind", ["preview"])[0]
            path = session.output_path if kind == "output" else session.preview_path
            if not path or not path.exists():
                self._json({"error": "No PDF available"}, status=404)
                return
            download_name = session.filename if query.get("download", [""])[0] == "1" else None
            self._send_file(path, "application/pdf", download_name=download_name)
            return
        self._json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/extract":
                self._extract()
            elif parsed.path == "/preview":
                self._render(preview=True)
            elif parsed.path == "/export":
                self._render(preview=False)
            else:
                self._json({"error": "Not found"}, status=404)
        except Exception as exc:
            self._json({"error": str(exc)}, status=500)

    def _extract(self) -> None:
        form = self._form()
        session = SessionState()
        SESSIONS[session.root.name] = session
        files = form["pdf"] if isinstance(form["pdf"], list) else [form["pdf"]]
        for item in files:
            if not item.filename:
                continue
            path = session.root / _safe_name(item.filename)
            with path.open("wb") as handle:
                shutil.copyfileobj(item.file, handle)
            session.sources.append(_prepare_source(path, session))
        if not session.sources:
            raise ValueError("Upload at least one FAT PDF.")
        variant = _field(form, "variant") or "auto"
        summary = extract_fat_summary(session.sources, system_variant=variant)
        session.extracted_summary = summary
        session.current_summary = summary
        self._json({"session": session.root.name, "values": get_editable_values(summary), "stats": _stats(summary)})

    def _render(self, preview: bool) -> None:
        form = self._form()
        session_id = _field(form, "session")
        session = self._session(session_id)
        if not session.extracted_summary:
            raise ValueError("Extract a FAT report first.")
        values = json.loads(_field(form, "values") or "{}")
        summary = apply_review_edits(session.extracted_summary, values)
        observations = [line.strip() for line in (_field(form, "observations") or "").splitlines() if line.strip()]
        summary.observations = [Observation(text=line, owner="Reviewer", status="Reviewed") for line in observations]
        summary.picture_evidence = self._picture_evidence(form, session)
        out = session.root / ("preview.pdf" if preview else "qualitrol_fat_summary.pdf")
        write_visual_summary_pdf(summary, out)
        session.current_summary = summary
        session.filename = _suggested_filename(summary)
        if preview:
            session.preview_path = out
        else:
            session.output_path = out
        self._json({
            "session": session.root.name,
            "url": f"/file?session={session.root.name}&kind={'preview' if preview else 'output'}",
            "pages": _pdf_pages(out),
            "filename": session.filename,
            "stats": _stats(summary),
        })

    def _picture_evidence(self, form: cgi.FieldStorage, session: SessionState) -> list[PictureEvidence]:
        pictures: list[PictureEvidence] = []
        for index in range(1, 5):
            key = f"picture{index}"
            if key not in form:
                continue
            item = form[key]
            if isinstance(item, list):
                item = item[0]
            if not item.filename:
                continue
            suffix = Path(item.filename).suffix or ".png"
            path = session.root / f"picture-{index}{suffix}"
            with path.open("wb") as handle:
                shutil.copyfileobj(item.file, handle)
            pictures.append(PictureEvidence(path=str(path), caption=_field(form, f"caption{index}") or f"Picture {index}"))
        return pictures

    def _form(self) -> cgi.FieldStorage:
        return cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")})

    def _session(self, session_id: str | None) -> SessionState:
        if not session_id or session_id not in SESSIONS:
            raise ValueError("Session expired. Extract the FAT report again.")
        return SESSIONS[session_id]

    def _json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str, download_name: str | None = None) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _field(form: cgi.FieldStorage, key: str) -> str:
    if key not in form:
        return ""
    value = form[key]
    if isinstance(value, list):
        value = value[0]
    return value.value if isinstance(value.value, str) else ""


def _safe_name(name: str) -> str:
    return "".join(char for char in Path(name).name if char.isalnum() or char in " ._-").strip() or "upload.pdf"


def _prepare_source(path: Path, session: SessionState) -> Path:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return path
    if suffix == ".docx":
        converted = session.root / f"{path.stem}_converted.pdf"
        return docx_to_text_pdf(path, converted)
    raise ValueError("Upload a FAT report as PDF or Word .docx.")


def _safe_stem(value: str | None) -> str:
    stem = "".join(char for char in (value or "") if char.isalnum() or char in " _-").strip()
    return "_".join(stem.split()) or "Qualitrol"


def _suggested_filename(summary: FatSummary) -> str:
    seed = (
        summary.project.manufacturing_number
        or summary.project.contract_number
        or summary.equipment.equipment_tag
        or summary.fat_context.document_no
        or summary.project.project_name
    )
    return f"{_safe_stem(seed)}_FAT_Summary.pdf"


def _pdf_pages(path: Path) -> int:
    with fitz.open(path) as doc:
        return max(doc.page_count, 1)


def _stats(summary: FatSummary) -> dict[str, object]:
    return {
        "project": summary.project.project_name or summary.project.substation or "-",
        "variant": summary.system_variant.value,
        "checks": summary.test_coverage.detected_test_count,
        "observations": len(summary.observations),
        "pictures": len(summary.picture_evidence),
    }


def _open_browser(url: str) -> None:
    chrome = _find_chrome()
    if chrome:
        profile = WORK_DIR / "chrome-profile"
        profile.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(
            [str(chrome), f"--user-data-dir={profile}", f"--app={url}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    webbrowser.open(url)


def _find_chrome() -> Path | None:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    return next((path for path in candidates if path.exists()), None)


def main() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), AppHandler)
    url = f"http://127.0.0.1:{server.server_port}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.2)
    _open_browser(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
