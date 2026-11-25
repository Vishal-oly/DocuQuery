from io import BytesIO

import pytest

from docuquery import rag, tables
from docuquery.repository import Repository


def test_table_to_markdown_builds_pipes_and_skips_empty_rows():
    markdown = tables.table_to_markdown([
        ["Model", "Accuracy"],
        ["DocuQuery", "0.92"],
        ["", ""],
        ["Baseline", None],
    ])
    assert markdown.splitlines()[0] == "| Model | Accuracy |"
    assert "| DocuQuery | 0.92 |" in markdown
    assert "| Baseline |  |" in markdown
    assert len(markdown.splitlines()) == 4


def test_table_to_markdown_escapes_pipes_inside_cells():
    markdown = tables.table_to_markdown([["A|B", "C"], ["1", "2"]])
    assert "A/B" in markdown


def test_extract_table_chunks_is_optional(monkeypatch):
    monkeypatch.setattr(tables, "tables_available", lambda: False)
    assert tables.extract_table_chunks(b"%PDF-1.4 fake") == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("F1 = 2PR/(P+R)", True),
        ("accuracy = 0.92 ± 0.03 over 5 folds", True),
        ("The model was trained for three epochs.", False),
        ("we compare two samples of students", False),
    ],
)
def test_formula_detection(text, expected):
    assert tables.looks_like_formula(text) is expected


def test_boost_data_chunks_prefers_tables_for_number_questions():
    chunks = [
        {"content": "prose", "similarity": 0.70, "kind": "text"},
        {"content": "table", "similarity": 0.66, "kind": "table"},
    ]
    boosted = rag.boost_data_chunks("what accuracy did the table report?", chunks)
    assert boosted[0]["content"] == "table"
    unchanged = rag.boost_data_chunks("what is the main idea?", chunks)
    assert unchanged[0]["content"] == "prose"


def test_format_context_labels_table_and_formula_chunks():
    context = rag.format_context([
        {"page_number": 3, "section": "Result", "content": "| a | b |", "kind": "table"},
        {"page_number": 4, "section": "Method", "content": "y = mx + c", "kind": "formula"},
    ])
    assert "p. 3 | Result | table]" in context
    assert "p. 4 | Method | equation/values]" in context


def test_repository_roundtrips_chunk_kind(tmp_path):
    repository = Repository({
        "LOCAL_DB_PATH": str(tmp_path / "kinds.sqlite3"),
        "EMBEDDING_DIMENSION": 2,
    })
    repository.save_paper({
        "id": "paper-1", "session_id": "s", "title": "T", "filename": "t.pdf",
        "page_count": 1, "summary": {},
    })
    repository.save_chunks([
        {"id": "c1", "paper_id": "paper-1", "session_id": "s", "page_number": 1,
         "section": "Table 1", "content": "| a | b |", "kind": "table", "embedding": [1.0, 0.0]},
        {"id": "c2", "paper_id": "paper-1", "session_id": "s", "page_number": 1,
         "section": "Text", "content": "plain words", "embedding": [0.0, 1.0]},
    ])
    stored = {chunk["id"]: chunk for chunk in repository.list_chunks("s", "paper-1")}
    assert stored["c1"]["kind"] == "table"
    assert stored["c2"]["kind"] == "text"


def test_extracts_a_real_table_with_pdfplumber():
    pytest.importorskip("pdfplumber")
    fpdf = pytest.importorskip("fpdf")

    pdf = fpdf.FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, "Results", new_x="LMARGIN", new_y="NEXT")
    with pdf.table() as table:
        for row_values in (["Model", "Accuracy"], ["DocuQuery", "0.92"], ["Baseline", "0.68"]):
            row = table.row()
            for value in row_values:
                row.cell(value)
    data = BytesIO(pdf.output())

    chunks = tables.extract_table_chunks(data.getvalue())
    assert chunks and chunks[0]["kind"] == "table"
    assert "| DocuQuery | 0.92 |" in chunks[0]["content"]
