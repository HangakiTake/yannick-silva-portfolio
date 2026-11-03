"""PDF text extraction via pdfplumber. Image-only files return an empty string."""

from __future__ import annotations

import io


def extract_pdf_text(pdf_bytes: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as document:
        pages = [(page.extract_text() or "") for page in document.pages]
    return "\n".join(pages)
