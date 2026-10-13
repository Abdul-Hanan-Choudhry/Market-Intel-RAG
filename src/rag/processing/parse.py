"""Turn any RawDocument into plain text, whatever format it arrived in."""

import re

import pymupdf
import trafilatura

from rag.config import settings
from rag.ingest.models import RawDocument

pymupdf.TOOLS.mupdf_display_errors(False)


def pdf_to_text(path) -> str:
    with pymupdf.open(path) as pdf:
        pages = [page.get_text("text", sort=True) for page in pdf]
    text = "\n\n".join(pages)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join words hyphenated across lines
    # PDF lines are layout lines, not paragraphs: merge lines unless separated by a blank line.
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text)]
    return "\n".join(p for p in paragraphs if p)


def extract_text(doc: RawDocument) -> str:
    if doc.file_path:
        path = settings.data_dir / doc.file_path
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return pdf_to_text(path)
        raw = path.read_text(encoding="utf-8", errors="ignore")
        if suffix in {".html", ".htm"}:
            return trafilatura.extract(raw, include_tables=True) or ""
        return raw
    return doc.text
