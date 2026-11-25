"""PDF text extraction, lightweight section detection, and page-aware chunking."""

from io import BytesIO
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from . import ocr, tables


class PDFProcessingError(ValueError):
    pass


SECTION_ALIASES = {
    "Abstract": ("abstract",),
    "Introduction": ("introduction", "background", "problem statement"),
    "Related Work": ("related work", "literature review", "previous work"),
    "Methods": (
        "method",
        "methods",
        "methodology",
        "materials and methods",
        "experimental setup",
        "approach",
    ),
    "Data": ("data", "dataset", "datasets", "materials"),
    "Results": ("results", "experiments", "evaluation", "findings"),
    "Discussion": ("discussion",),
    "Limitations": ("limitations", "threats to validity", "future work"),
    "Conclusion": ("conclusion", "conclusions", "summary and conclusions"),
    "References": ("references", "bibliography"),
}

_NUMBER_PREFIX = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?\s+|[IVXLC]+[.)]?\s+)?")


def _detect_heading(line: str) -> str | None:
    candidate = _NUMBER_PREFIX.sub("", line).strip().strip(" :\t-–—")
    if not candidate or len(candidate) > 90:
        return None
    words = candidate.split()
    if len(words) > 8:
        return None
    lowered = re.sub(r"\s+", " ", candidate.lower())
    for section, aliases in SECTION_ALIASES.items():
        for alias in aliases:
            if lowered == alias:
                return section
            # "Abstract: this paper studies ..." is prose, not a heading; only a
            # section label with little or no trailing text should split the page.
            if lowered.startswith(alias + ":"):
                trailing = lowered[len(alias) + 1:].strip()
                if not trailing or len(trailing.split()) <= 2:
                    return section
            # Headings such as "3.1 Results and analysis" are common in papers.
            if lowered.startswith(alias + " ") and len(words) <= 6:
                return section
    return None


def _split_sections(page_text: str, inherited_section: str = "Overview") -> tuple[list[tuple[str, str]], str]:
    blocks: list[tuple[str, str]] = []
    current_section = inherited_section
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            blocks.append((current_section, text))
        buffer.clear()

    for raw_line in page_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            if buffer and buffer[-1] != "":
                buffer.append("")
            continue
        heading = _detect_heading(line)
        if heading:
            flush()
            current_section = heading
            continue
        buffer.append(line)
    flush()
    return blocks, current_section


def _chunk_text(text: str, chunk_size: int = 1250, overlap: int = 180) -> list[str]:
    cleaned = re.sub(r"[ \t]+", " ", text).strip()
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        if end < len(cleaned):
            floor = start + int(chunk_size * 0.62)
            boundary = max(
                cleaned.rfind(". ", floor, end),
                cleaned.rfind("? ", floor, end),
                cleaned.rfind("! ", floor, end),
                cleaned.rfind("\n", floor, end),
            )
            if boundary >= floor:
                end = boundary + 1
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(cleaned):
            break
        next_start = max(start + 1, end - overlap)
        start = next_start
    return chunks


def _guess_title(first_page_text: str, filename: str) -> str:
    for line in first_page_text.splitlines():
        candidate = re.sub(r"\s+", " ", line).strip(" \t-–—")
        if not candidate or len(candidate) < 5 or len(candidate) > 180:
            continue
        if candidate.lower() in {"abstract", "research article", "article"}:
            continue
        if len(candidate.split()) <= 24 and not candidate.lower().startswith(("doi:", "https://")):
            return candidate
    return Path(filename).stem.replace("_", " ").replace("-", " ").strip() or "Untitled paper"


def _sanitize_text(text: str) -> str:
    """Strip characters that Postgres text/jsonb cannot store (notably NUL \\x00).

    pypdf can emit null bytes from broken PDF text layers; Postgres rejects them
    with 'unsupported Unicode escape sequence'. Tab/newline/carriage-return stay.
    """
    if not text:
        return text or ""
    return text.translate({i: None for i in list(range(0, 9)) + [11, 12] + list(range(14, 32))})


def _ocr_missing_pages(file_bytes: bytes, raw_pages: list[str], max_pages: int) -> tuple[list[str], int]:
    """Fill pages that had no selectable text using the optional OCR add-on."""
    empty = [number for number, text in enumerate(raw_pages, start=1)
             if len(text.strip()) < ocr.MIN_PAGE_CHARS]
    if not empty or max_pages <= 0 or not ocr.enabled():
        return raw_pages, 0
    try:
        recognised = ocr.ocr_pages(file_bytes, empty[:max_pages])
    except Exception:
        return raw_pages, 0
    updated = 0
    for number, text in recognised.items():
        if text.strip():
            raw_pages[number - 1] = _sanitize_text(text)
            updated += 1
    return raw_pages, updated


def _drop_flattened_duplicates(
    chunks: list[dict[str, Any]], table_chunks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Remove prose chunks that are just a table flattened into loose words."""
    by_page: dict[int, str] = {}
    for table in table_chunks:
        page = int(table["page_number"])
        by_page[page] = by_page.get(page, "") + " " + table["content"]
    vocab = {
        page: set(re.findall(r"[a-z0-9.]+", text.lower())) for page, text in by_page.items()
    }
    kept = []
    for chunk in chunks:
        page = int(chunk["page_number"])
        words = set(re.findall(r"[a-z0-9.]+", chunk["content"].lower()))
        covered = len(words & vocab.get(page, set())) / max(len(words), 1)
        if chunk.get("kind") != "table" and covered >= 0.7 and len(words) <= 40:
            continue
        kept.append(chunk)
    return kept


def parse_pdf_bytes(
    file_bytes: bytes,
    filename: str,
    chunk_size: int = 1250,
    overlap: int = 180,
    ocr_max_pages: int = ocr.DEFAULT_MAX_PAGES,
    extract_tables: bool = True,
) -> dict[str, Any]:
    if not filename.lower().endswith(".pdf"):
        raise PDFProcessingError("Please upload a PDF file.")
    if not file_bytes or not file_bytes.startswith(b"%PDF-"):
        raise PDFProcessingError("This file does not look like a valid PDF.")

    try:
        reader = PdfReader(BytesIO(file_bytes), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise PDFProcessingError("This PDF is password-protected and cannot be opened.") from exc
        total_pages = len(reader.pages)
        if total_pages == 0:
            raise PDFProcessingError("The PDF has no pages.")
        raw_pages: list[str] = []
        for page in reader.pages:
            try:
                raw_pages.append(_sanitize_text(page.extract_text() or ""))
            except Exception:
                raw_pages.append("")

        # Scanned pages have no text layer; the optional add-on reads them from pixels.
        raw_pages, ocr_pages = _ocr_missing_pages(file_bytes, raw_pages, ocr_max_pages)

        chunk_records: list[dict[str, Any]] = []
        current_section = "Overview"
        for page_number, page_text in enumerate(raw_pages, start=1):
            if not page_text.strip():
                continue
            blocks, current_section = _split_sections(page_text, current_section)
            for section, block in blocks:
                for piece in _chunk_text(block, chunk_size=chunk_size, overlap=overlap):
                    if len(piece) < 20:
                        continue
                    chunk_records.append(
                        {
                            "page_number": page_number,
                            "section": section,
                            "content": piece,
                            "kind": tables.tag_chunk_kind(piece),
                        }
                    )
    except PDFProcessingError:
        raise
    except Exception as exc:
        raise PDFProcessingError(f"Could not read this PDF: {exc}") from exc

    if extract_tables and tables.tables_available():
        # Numbers live in tables; keep them as Markdown so the model can quote them.
        known = {(c["page_number"], c["content"][:120]) for c in chunk_records}
        table_chunks = [
            extra for extra in tables.extract_table_chunks(file_bytes, chunk_size=chunk_size)
            if (extra["page_number"], extra["content"][:120]) not in known
        ]
        if table_chunks:
            chunk_records = _drop_flattened_duplicates(chunk_records, table_chunks)
            chunk_records.extend(table_chunks)

    if not chunk_records:
        if ocr.available():
            raise PDFProcessingError(
                "No readable text was found, even with OCR. The scan may be too low quality."
            )
        raise PDFProcessingError(
            "No selectable text was found. This looks like a scanned PDF — install the optional "
            "OCR add-on (pip install -r requirements-ocr.txt) to read image-only PDFs."
        )

    joined_text = "\n".join(raw_pages)
    return {
        "title": _sanitize_text(_guess_title(raw_pages[0] if raw_pages else "", filename)),
        "page_count": total_pages,
        "text_char_count": len(joined_text),
        "ocr_pages": ocr_pages,
        "table_chunks": sum(1 for c in chunk_records if c.get("kind") == "table"),
        "chunks": chunk_records,
    }
