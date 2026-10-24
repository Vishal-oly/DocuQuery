import pytest

from docuquery.pdf_processing import PDFProcessingError, _chunk_text, _split_sections, parse_pdf_bytes


def test_sections_are_detected_and_inherited():
    blocks, current = _split_sections("Abstract\nThe paper introduces a new method.\n\n2 Methods\nWe use a controlled experiment.")
    assert blocks[0][0] == "Abstract"
    assert "new method" in blocks[0][1]
    assert blocks[1][0] == "Methods"
    assert current == "Methods"


def test_long_text_chunks_overlap_without_empty_parts():
    text = "Sentence with enough words to form a useful passage. " * 80
    chunks = _chunk_text(text, chunk_size=240, overlap=40)
    assert len(chunks) > 2
    assert all(chunks)
    assert all(len(chunk) <= 240 for chunk in chunks)


def test_non_pdf_is_rejected():
    with pytest.raises(PDFProcessingError, match="valid PDF"):
        parse_pdf_bytes(b"not a pdf", "article.pdf")


def test_sanitize_text_strips_null_and_control_chars():
    from docuquery.pdf_processing import _sanitize_text

    # NUL and other C0 control chars break Postgres text storage; keep newlines/tabs.
    dirty = "Hel\x00lo\x07 world\x1f!\nTab\there\r"
    assert _sanitize_text(dirty) == "Hello world!\nTab\there\r"
    assert _sanitize_text("") == ""
    assert _sanitize_text(None) == ""
