from io import BytesIO

import pytest
from pypdf import PdfWriter

from docuquery import ocr, pdf_processing


def blank_pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_ocr_pages_is_skipped_when_addon_missing(monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: False)
    assert ocr.enabled() is False
    raw, count = pdf_processing._ocr_missing_pages(blank_pdf(), [""], 20)
    assert count == 0 and raw == [""]


def test_ocr_pages_disabled_by_env(monkeypatch):
    monkeypatch.setenv("OCR_ENABLED", "false")
    assert ocr.enabled() is False


def test_ocr_result_cleans_recogniser_output(monkeypatch):
    calls = {}

    class FakeDocument:
        def __init__(self, data):
            calls["data"] = data

        def __len__(self):
            return 1

        def __getitem__(self, index):
            class Page:
                def render(self, scale):
                    class Bitmap:
                        def to_pil(self):
                            return "image"

                    return Bitmap()

            return Page()

        def close(self):
            calls["closed"] = True

    class FakePdfium:
        PdfDocument = FakeDocument

    monkeypatch.setitem(__import__("sys").modules, "pypdfium2", FakePdfium)

    def fake_engine(image):
        assert image == "image"
        return [[[0, 0, 1, 1], "First line", 0.9], [[0, 0, 1, 1], "  ", 0.1],
                [[0, 0, 1, 1], "Second line", 0.8]], 0.42

    result = ocr.ocr_pages(b"%PDF-fake", [1], engine=fake_engine)
    assert result == {1: "First line Second line"}
    assert calls["closed"] is True


def test_parse_pdf_uses_ocr_for_scanned_pages(monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(ocr, "enabled", lambda: True)

    def fake_ocr(file_bytes, page_numbers, **kwargs):
        assert page_numbers == [1, 2]
        return {1: "Abstract: this paper studies offline retrieval augmented generation.",
                2: "Results: the local model answered 92 percent of questions correctly."}

    monkeypatch.setattr(ocr, "ocr_pages", fake_ocr)

    parsed = pdf_processing.parse_pdf_bytes(
        blank_pdf(2), "scan.pdf", ocr_max_pages=5)
    assert parsed["ocr_pages"] == 2
    assert len(parsed["chunks"]) >= 1
    assert any("offline retrieval" in chunk["content"] for chunk in parsed["chunks"])


def test_parse_pdf_without_ocr_explains_the_addon(monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: False)
    monkeypatch.setattr(ocr, "enabled", lambda: False)
    with pytest.raises(pdf_processing.PDFProcessingError, match="requirements-ocr"):
        pdf_processing.parse_pdf_bytes(blank_pdf(1), "scan.pdf")
