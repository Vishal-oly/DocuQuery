"""Optional OCR for scanned PDF pages.

The core app deliberately ships without OCR so a fresh install stays small and fully
offline on a modest laptop. When the optional add-on is installed:

    pip install -r requirements-ocr.txt

scanned pages are rendered with **pypdfium2** and recognised with **RapidOCR**
(ONNX runtime, models bundled in the wheel). Both are ordinary pip packages, so no
external Tesseract/Poppler binaries are needed, and OCR keeps working offline.

Everything here is best-effort: if the add-on is missing or fails, the caller falls
back to the normal "no selectable text" behaviour instead of crashing.
"""

from __future__ import annotations

import os
from typing import Any

MIN_PAGE_CHARS = 40
DEFAULT_MAX_PAGES = 20
RENDER_SCALE = 2.0


class OCRError(RuntimeError):
    """Raised when the optional OCR stack is missing or cannot read a page."""


def enabled() -> bool:
    if os.environ.get("OCR_ENABLED", "true").strip().lower() in {"0", "false", "no"}:
        return False
    return available()


def available() -> bool:
    """True when both optional packages can be imported."""
    try:
        import pypdfium2  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
    except Exception:
        return False
    return True


def _engine() -> Any:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:  # pragma: no cover - depends on optional install
        raise OCRError(
            "OCR is not installed. Run: pip install -r requirements-ocr.txt"
        ) from exc
    return RapidOCR()


def ocr_pages(file_bytes: bytes, page_numbers: list[int], scale: float = RENDER_SCALE,
              engine: Any = None) -> dict[int, str]:
    """OCR the requested 1-based page numbers and return ``{page: text}``."""
    if not page_numbers:
        return {}
    try:
        import pypdfium2 as pdfium
    except Exception as exc:  # pragma: no cover - depends on optional install
        raise OCRError(
            "OCR is not installed. Run: pip install -r requirements-ocr.txt"
        ) from exc

    recogniser = engine or _engine()
    document = pdfium.PdfDocument(file_bytes)
    results: dict[int, str] = {}
    try:
        for number in page_numbers:
            if number < 1 or number > len(document):
                continue
            page = document[number - 1]
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil()
            try:
                found, _timing = recogniser(image)
            except TypeError:  # some versions return only the result list
                found = recogniser(image)
            lines = []
            for item in found or []:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    text = str(item[1]).strip()
                    if text:
                        lines.append(text)
            results[number] = " ".join(lines)
    finally:
        document.close()
    return results
