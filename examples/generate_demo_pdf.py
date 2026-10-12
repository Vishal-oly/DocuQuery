"""Create a tiny synthetic PDF for testing the upload flow; no extra package required."""

from pathlib import Path


def create_pdf() -> bytes:
    lines = [
        "Demo Study: Page-Aware Retrieval for Scientific Papers",
        "Abstract",
        "This synthetic example tests a page-aware retrieval workflow for research-paper PDFs.",
        "It is provided only to test DocuQuery; every result and number is fictional.",
        "Introduction",
        "Scientific articles can be difficult to review when evidence is spread over many pages.",
        "Methods",
        "We use overlapping text chunks, section labels, and page metadata for evidence retrieval.",
        "A small synthetic benchmark contains 120 papers and 600 manually written questions.",
        "Results",
        "In this fictional test, page-aware retrieval improves evidence precision by 14 percent.",
        "Limitations",
        "This invented example uses only selectable English text and does not evaluate scanned PDFs.",
        "Conclusion",
        "Page references can help readers verify summaries against the original article.",
    ]
    y = 750
    operations = ["BT", "/F1 10 Tf"]
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        operations.append(f"1 0 0 1 48 {y} Tm ({escaped}) Tj")
        y -= 42
    operations.append("ET")
    stream = "\n".join(operations).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode())
        data.extend(obj)
        data.extend(b"\nendobj\n")
    xref_offset = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(data)


if __name__ == "__main__":
    output = Path(__file__).with_name("sample_scientific_article.pdf")
    output.write_bytes(create_pdf())
    print(f"Wrote synthetic test PDF: {output}")
