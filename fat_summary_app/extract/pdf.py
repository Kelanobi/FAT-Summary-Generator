from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True)
class PdfPage:
    number: int
    text: str


@dataclass(frozen=True)
class PdfDocument:
    path: Path
    pages: list[PdfPage]
    sha256: str

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)


def read_pdf(path: str | Path) -> PdfDocument:
    pdf_path = Path(path)
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    doc = fitz.open(pdf_path)
    pages = [PdfPage(number=index + 1, text=page.get_text("text") or "") for index, page in enumerate(doc)]
    return PdfDocument(path=pdf_path, pages=pages, sha256=digest)

