"""Table extraction (optional) and formula detection for research PDFs.

Tables in papers hold the numbers people actually ask about ("what was the accuracy?"),
but plain text extraction flattens them into unusable word soup. When ``pdfplumber`` is
installed we rebuild each table as Markdown, which a small local model can read and cite.

Formula detection is pure-Python and always on: equations extracted from a text layer
usually arrive as symbol-heavy fragments, so they are tagged ``kind="formula"`` and
retrieved separately instead of being buried inside prose chunks.
"""

from __future__ import annotations

from io import BytesIO
import re
from typing import Any

MAX_TABLES_PER_PAPER = 40
MAX_CHARS_PER_TABLE = 2400

_MATH_MARKERS = re.compile(r"[=≈≤≥±∑∏∫√∂∞µμαβγδθλσφωΔΣΩ^_{}\\]")
_FORMULA_LINE = re.compile(r"^\s*[A-Za-z0-9\s()\[\]{}+\-*/^_=.,'′]*[=≈≤≥][^.]{0,80}$")


def tables_available() -> bool:
    """pdfplumber is an optional dependency; the app works without it."""
    try:
        import pdfplumber  # noqa: F401
    except Exception:
        return False
    return True


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text.replace("|", "/")


def table_to_markdown(rows: list[list[Any]]) -> str:
    cleaned = [[_clean_cell(cell) for cell in row] for row in rows if row]
    cleaned = [row for row in cleaned if any(cell for cell in row)]
    if len(cleaned) < 2:
        return ""
    width = max(len(row) for row in cleaned)
    padded = [row + [""] * (width - len(row)) for row in cleaned]
    header, body = padded[0], padded[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def extract_table_chunks(
    file_bytes: bytes,
    chunk_size: int = 1250,
    max_tables: int = MAX_TABLES_PER_PAPER,
) -> list[dict[str, Any]]:
    """Return Markdown table chunks, or an empty list when pdfplumber is missing."""
    if not tables_available() or max_tables <= 0:
        return []
    import pdfplumber  # optional dependency, imported lazily

    chunks: list[dict[str, Any]] = []
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                for index, table in enumerate(page.extract_tables() or [], start=1):
                    if len(chunks) >= max_tables:
                        return chunks
                    markdown = table_to_markdown(table)[:MAX_CHARS_PER_TABLE]
                    if len(markdown) < 40:
                        continue
                    for piece in _split(markdown, chunk_size):
                        chunks.append(
                            {
                                "page_number": page_number,
                                "section": f"Table {index}",
                                "content": piece,
                                "kind": "table",
                            }
                        )
    except Exception:
        # A malformed table should never fail an upload; text extraction already worked.
        return chunks
    return chunks


def _split(text: str, chunk_size: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    pieces, current = [], []
    for line in text.splitlines():
        current.append(line)
        if sum(len(item) + 1 for item in current) >= chunk_size:
            pieces.append("\n".join(current))
            current = [line] if line.startswith("|") and line.count("|") > 2 else []
    if current:
        pieces.append("\n".join(current))
    return [piece for piece in pieces if piece.strip()]


def looks_like_formula(text: str) -> bool:
    """Heuristic: symbol-dense fragments and standalone equations."""
    stripped = text.strip()
    if len(stripped) < 8:
        return False
    markers = len(_MATH_MARKERS.findall(stripped))
    density = markers / max(len(stripped), 1)
    if markers >= 3 and density > 0.02:
        return True
    if "=" in stripped and markers >= 2 and len(stripped) <= 200:
        return True
    return bool(_FORMULA_LINE.match(stripped))


def tag_chunk_kind(text: str) -> str:
    return "formula" if looks_like_formula(text) else "text"
