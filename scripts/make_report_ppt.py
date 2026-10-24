"""Generate the minor-project report (.docx) and viva presentation (.pptx).

Run from the repo root:  python3 scripts/make_report_ppt.py
Outputs land in docs/.
"""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from pptx import Presentation
from pptx.dml.color import RGBColor as PRGB
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches as PInches, Pt as PPt

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

PURPLE = RGBColor(0x5B, 0x4B, 0xC4)
PURPLE_HEX = 0x5B4BC4
GREEN_HEX = 0x2E9E6F
INK_HEX = 0x1F2430

# ---------------------------------------------------------------------------
# Report (.docx)
# ---------------------------------------------------------------------------

def _p(doc, text="", bold=False, size=11, align=None, space_after=6, color=None):
    para = doc.add_paragraph()
    run = para.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = color
    if align == "center":
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_after = Pt(space_after)
    return para


def _bullets(doc, items):
    for item in items:
        para = doc.add_paragraph(style="List Bullet")
        run = para.add_run(item)
        run.font.size = Pt(11)


def _table(doc, headers, rows, widths=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Grid Accent 1"
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = str(value)
    doc.add_paragraph()


def build_report():
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # ----- Title page -----
    for _ in range(4):
        _p(doc, "", size=14)
    _p(doc, "MINOR PROJECT REPORT", bold=True, size=16, align="center")
    _p(doc, "", size=10)
    _p(doc, "DocuQuery", bold=True, size=28, align="center", color=PURPLE)
    _p(doc, "A Retrieval-Augmented Web Assistant for Scientific Paper PDFs",
       bold=True, size=14, align="center")
    _p(doc, "", size=12)
    _p(doc, "Submitted by", size=12, align="center")
    _p(doc, "[Your Name]  —  [Roll Number]", bold=True, size=13, align="center")
    _p(doc, "[Batch / Semester]", size=12, align="center")
    _p(doc, "", size=10)
    _p(doc, "Under the guidance of", size=12, align="center")
    _p(doc, "[Guide Name], [Designation]", bold=True, size=13, align="center")
    _p(doc, "", size=10)
    _p(doc, "Department of [Your Department]", size=12, align="center")
    _p(doc, "[Your College / University]", size=12, align="center")
    _p(doc, "Academic Year 2025–2026", size=12, align="center")
    doc.add_page_break()

    # ----- Certificate & Declaration -----
    _p(doc, "CERTIFICATE", bold=True, size=16, align="center")
    _p(doc, "")
    _p(doc, "This is to certify that the project entitled “DocuQuery: A Retrieval-Augmented "
            "Web Assistant for Scientific Paper PDFs” is a bonafide work carried out by "
            "[Your Name] ([Roll Number]) in partial fulfillment of the requirements for the award of "
            "the degree of [Your Degree] in [Your Department] during the academic year 2025–2026.")
    _p(doc, "")
    _p(doc, "[Guide Name]                                                     [Head of Department]", size=11)
    doc.add_page_break()

    _p(doc, "DECLARATION", bold=True, size=16, align="center")
    _p(doc, "")
    _p(doc, "I hereby declare that the project work embodied in this report entitled “DocuQuery: "
            "A Retrieval-Augmented Web Assistant for Scientific Paper PDFs” is the outcome of my "
            "own work done under the guidance of [Guide Name]. The matter embodied in this project "
            "has not been submitted, in whole or in part, for the award of any other degree or diploma.")
    _p(doc, "")
    _p(doc, "Place: [City]                                                                 [Your Name]", size=11)
    doc.add_page_break()

    # ----- Abstract -----
    doc.add_heading("Abstract", level=1)
    _p(doc, "Scientific papers contain detailed methods, results, and limitations that are difficult "
            "to locate quickly. Short generic summaries often hide the methodology, data, and evidence "
            "behind a claim. DocuQuery is a web-based reading assistant that accepts a research-paper "
            "PDF, extracts its text page by page, splits it into searchable passages, and retrieves "
            "the evidence relevant to a structured research brief or to a user's question.")
    _p(doc, "Every answer and every brief field is shown together with page- and section-linked source "
            "excerpts, so readers can verify claims against the original article. The frontend uses "
            "HTML, CSS, JavaScript and Bootstrap; the backend is Python with Flask. Groq provides "
            "language-model generation, and Supabase PostgreSQL with pgvector is the persistent store, "
            "with a local SQLite mode for credential-free demonstrations. The system includes user "
            "authentication (email/password and optional Google Sign-In), a paper library, downloadable "
            "summaries, and per-account history management.")
    _p(doc, "Keywords: Retrieval-Augmented Generation, Large Language Models, pgvector, Flask, "
            "Scientific Document Understanding, Groq.")

    # ----- Chapter 1 -----
    doc.add_heading("1. Introduction", level=1)
    doc.add_heading("1.1 Motivation", level=2)
    _p(doc, "Students and researchers spend a large part of their time reading PDFs to find a paper's "
            "objective, dataset, methodology, findings and limitations. Generic chat tools can summarize "
            "a paper but usually cannot show WHERE in the paper the answer came from. DocuQuery focuses "
            "on this gap: every generated sentence is grounded in retrieved passages and carries page "
            "citations.")
    doc.add_heading("1.2 Problem Statement", level=2)
    _p(doc, "Reading full research articles is time-consuming, and short summaries may hide the "
            "methodology, data, limitations, or evidence behind a claim. Readers also need to locate "
            "the exact source passage that supports an answer. DocuQuery addresses these needs by "
            "combining retrieval with structured generation and by displaying page and section "
            "references with every result.")
    doc.add_heading("1.3 Objectives", level=2)
    _bullets(doc, [
        "Accept and validate scientific-paper PDF uploads.",
        "Extract selectable PDF text while preserving page numbers.",
        "Detect scientific sections and split text into overlapping passages.",
        "Create 384-dimensional passage vectors (offline feature hashing, optional MiniLM).",
        "Store papers, summaries, passages and vectors in Supabase/pgvector (or SQLite locally).",
        "Retrieve relevant evidence for brief fields and user questions.",
        "Generate structured research briefs and grounded answers with Groq when configured.",
        "Provide user accounts with secure password storage, sessions and Google Sign-In.",
        "Display source excerpts and page references in a responsive, accessible workspace.",
    ])
    doc.add_heading("1.4 Scope", level=2)
    _p(doc, "The prototype focuses on selectable-text journal-style PDFs. It provides authentication, "
            "a workspace with PDF upload, a research brief, an evidence trail, question answering "
            "(“Ask This Paper”), a paper library, downloadable summaries, and profile management "
            "(name, password, uploaded files, clear history). OCR for scanned PDFs, multi-paper "
            "comparison and table/figure extraction are kept as future enhancements.")

    # ----- Chapter 2 -----
    doc.add_heading("2. Background", level=1)
    doc.add_heading("2.1 Retrieval-Augmented Generation (RAG)", level=2)
    _p(doc, "RAG (Lewis et al., 2020) combines a retriever with a generator: instead of relying on "
            "memorized knowledge, the system searches a document collection for the passages most "
            "relevant to a query and gives them to a language model as context. DocuQuery applies RAG "
            "per paper: each uploaded PDF becomes its own searchable collection of passages.")
    doc.add_heading("2.2 Vector Search and pgvector", level=2)
    _p(doc, "Passages are embedded as 384-dimensional vectors. Similarity search uses cosine distance, "
            "computed inside PostgreSQL by the pgvector extension (HNSW index), through a stored "
            "function match_paper_chunks. Feature hashing gives deterministic offline embeddings; "
            "Sentence-Transformers MiniLM is supported as an optional upgrade.")
    doc.add_heading("2.3 Large Language Models via Groq", level=2)
    _p(doc, "Groq's Chat Completions API (OpenAI-compatible) generates the structured brief as JSON and "
            "answers questions strictly from the retrieved context. Without an API key the system still "
            "works in a clearly-labelled extractive preview mode that quotes the paper's own sentences.")

    # ----- Chapter 3 -----
    doc.add_heading("3. System Analysis", level=1)
    doc.add_heading("3.1 Functional Requirements", level=2)
    _bullets(doc, [
        "FR1: Register / login / logout; optional one-tap Google Sign-In.",
        "FR2: Upload a PDF (validated, ≤ 20 MB) and index its passages.",
        "FR3: Generate a structured research brief with page citations.",
        "FR4: Show an evidence trail of the retrieved source excerpts.",
        "FR5: Answer free-form questions about the selected paper with citations.",
        "FR6: List, reopen and delete papers in a per-account library.",
        "FR7: Download summaries as Markdown, Text or JSON.",
        "FR8: Profile management: change name/password, view uploaded files, clear history.",
        "FR9: Password reset via a time-limited reset code.",
    ])
    doc.add_heading("3.2 Non-Functional Requirements", level=2)
    _bullets(doc, [
        "Security: hashed passwords (Werkzeug), signed session tokens, per-account data isolation, "
        "RLS-protected database tables.",
        "Performance: chunk-level retrieval completes in milliseconds; brief generation in seconds.",
        "Usability: responsive single-page workspace; works in sandboxed preview iframes "
        "(token-in-URL authentication).",
        "Portability: runs with SQLite + extractive mode with zero credentials, or with Supabase + Groq.",
        "Testability: 33 automated pytest cases covering auth, repository, RAG, PDF parsing and APIs.",
    ])
    doc.add_heading("3.3 Feasibility", level=2)
    _p(doc, "Technical: all components are open-source or free-tier (Flask, pypdf, Supabase free plan, "
            "Groq free tier). Operational: the app runs with one command (python run.py). Economic: "
            "the complete stack costs ₹0 for development and demonstration.")

    # ----- Chapter 4 -----
    doc.add_heading("4. System Design", level=1)
    doc.add_heading("4.1 Architecture", level=2)
    _p(doc, "DocuQuery follows a three-layer architecture:")
    _table(doc, ["Layer", "Components"], [
        ["Presentation", "Landing, login/register, workspace, summaries, profile (HTML/CSS/JS + Bootstrap)"],
        ["Application (Flask routes)", "Auth & tokens, upload pipeline, brief/summary, Q&A, library, downloads, profile, clear-history"],
        ["Data", "Repository abstraction: Supabase PostgreSQL + pgvector (production) or SQLite (demo)"],
        ["Intelligence", "RAG service (retrieval + context building), Groq adapter, extractive fallback, embedding adapter"],
    ])
    doc.add_heading("4.2 Data Model (ER)", level=2)
    _table(doc, ["Entity", "Key attributes"], [
        ["users", "id (uuid PK), name, email (unique), password_hash, created_at, reset_token, reset_expires"],
        ["papers", "id (uuid PK), session_id (FK users), title, filename, page_count, created_at, summary (jsonb), file_path, file_size"],
        ["paper_chunks", "id (uuid PK), paper_id (FK papers, cascade), session_id, page_number, section, content, embedding vector(384)"],
    ])
    _p(doc, "Relationships: users 1—N papers; papers 1—N paper_chunks (delete cascades). The "
            "match_paper_chunks(query_embedding, session, paper, k) function performs indexed "
            "cosine-similarity retrieval.")
    doc.add_heading("4.3 Processing Workflow", level=2)
    _p(doc, "Research PDF → file validation → page-wise text extraction (with control-character "
            "sanitisation for PostgreSQL) → section detection → overlapping chunking (~1,250 chars, "
            "180 overlap) → 384-d embeddings → storage → similarity retrieval (top-k) → Groq structured "
            "brief / grounded answer → workspace with evidence trail and page citations.")

    # ----- Chapter 5 -----
    doc.add_heading("5. Implementation", level=1)
    doc.add_heading("5.1 Module Overview", level=2)
    _table(doc, ["Module", "File(s)", "Responsibility"], [
        ["Web workspace", "index.html, app.js", "Upload, brief, evidence trail, chat, library"],
        ["Auth", "routes.py, auth.js, dq.js", "Register/login, signed tokens, Google Sign-In, password reset"],
        ["PDF processor", "pdf_processing.py", "Validation, extraction, section split, chunking, sanitisation"],
        ["Embeddings", "embeddings.py", "Feature hashing (default) / MiniLM adapter (384-d)"],
        ["RAG service", "rag.py", "Retrieval, context building, citations, brief/answer assembly"],
        ["LLM adapter", "llm.py", "Groq JSON brief + Q&A; extractive fallback"],
        ["Repository", "repository.py, storage.py", "Supabase/SQLite persistence; PDF file storage"],
        ["API", "routes.py", "30+ REST endpoints incl. downloads and clear-history"],
    ])
    doc.add_heading("5.2 Authentication Design", level=2)
    _p(doc, "Passwords are hashed with Werkzeug's scrypt-based generate_password_hash. Successful "
            "login issues a signed token (itsdangerous) accepted three ways — Authorization Bearer "
            "header, ?token= URL parameter, or cookie — which makes the app work inside sandboxed "
            "preview iframes where cookies and custom headers can be stripped. Google Sign-In verifies "
            "Google ID tokens server-side and auto-creates or joins accounts by verified email.")
    doc.add_heading("5.3 Retrieval and Generation", level=2)
    _p(doc, "Questions are embedded with the same adapter as the passages. The top-k passages "
            "(cosine similarity) form the context; the LLM is instructed to answer ONLY from that "
            "context and to cite pages like [p. 2]. The brief is generated as JSON with fixed fields "
            "(objective, dataset, methodology, key_findings, limitations, conclusion, overall_summary) "
            "so the UI can render it consistently with an evidence trail.")

    # ----- Chapter 6 -----
    doc.add_heading("6. Testing", level=1)
    _p(doc, "The project carries 33 automated tests (pytest) and was additionally verified through "
            "real browser end-to-end scripts (headless Chrome) exercising register → upload → brief → "
            "Q&A → download → profile → clear-history.")
    _table(doc, ["Test area", "What is verified"], [
        ["Auth (auth, token_auth, google_auth)", "Register/login/logout, token issue & expiry, Google verify/create/join, 401 handling"],
        ["Repository", "User CRUD, papers, chunks, reset tokens, SQLite ranking & isolation"],
        ["PDF processing", "Section detection, overlap chunking, invalid-file rejection, text sanitisation"],
        ["Embeddings", "Deterministic 384-d vectors, normalisation"],
        ["Features / API", "Upload, brief generation, Q&A, downloads, delete, clear-history, page limits"],
    ])
    _p(doc, "Result: 33/33 tests pass. Browser tests: 9/9 scenarios pass (sandboxed-iframe suite "
            "earlier verified 6/6 including the sign-in flow).")

    # ----- Chapter 7 -----
    doc.add_heading("7. Results", level=1)
    _bullets(doc, [
        "Upload of a 144-page survey paper indexes 887 passages in ~10 seconds.",
        "Research brief generation returns structured fields with page citations in seconds "
        "(Groq free tier).",
        "Q&A answers carry page + section references (e.g., “pre-training … [p. 26, Data]”).",
        "Multi-user accounts with isolated libraries; clear-history resets an account safely.",
        "Works in three environments: normal tab, third-party iframe, fully sandboxed iframe.",
        "Zero-cost stack: Supabase free tier + Groq free tier + open-source libraries.",
    ])

    # ----- Chapter 8 -----
    doc.add_heading("8. Future Enhancements", level=1)
    _bullets(doc, [
        "OCR support for scanned/image-only PDFs.",
        "Multi-paper comparison and cross-document question answering.",
        "BibTeX/RIS citation export and PDF export of the research brief.",
        "Email delivery for password reset (currently demo codes).",
        "Reranking and retrieval-quality evaluation against labelled question sets.",
        "Production deployment (gunicorn + managed hosting) and monitoring.",
    ])

    # ----- Chapter 9 -----
    doc.add_heading("9. Conclusion", level=1)
    _p(doc, "DocuQuery demonstrates that a retrieval-augmented pipeline can make scientific reading "
            "faster WITHOUT losing verifiability: every claim in a brief or answer points back to a "
            "page of the uploaded paper. The system is fully functional end-to-end, tested "
            "automatically, deployable at zero cost, and designed to degrade gracefully — it still "
            "works, with clearly labelled extractive answers, when no LLM key is configured.")

    # ----- References -----
    doc.add_heading("References", level=1)
    _bullets(doc, [
        "Lewis, P. et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS.",
        "Vaswani, A. et al. (2017). Attention Is All You Need. NeurIPS.",
        "Zhao, W. X. et al. (2023). A Survey of Large Language Models. arXiv:2303.18223.",
        "pgvector: Open-source vector similarity for Postgres — github.com/pgvector/pgvector",
        "Groq API Documentation — console.groq.com/docs",
        "Supabase Documentation — supabase.com/docs",
        "Flask Documentation — flask.palletsprojects.com",
        "pypdf Documentation — pypdf.readthedocs.io",
    ])

    out = DOCS / "DocuQuery_Project_Report.docx"
    doc.save(out)
    print("report ->", out)


# ---------------------------------------------------------------------------
# Presentation (.pptx)
# ---------------------------------------------------------------------------

def _slide(prs, title, subtitle=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    # top band
    band = slide.shapes.add_shape(1, Emu(0), Emu(0), prs.slide_width, PInches(1.15))
    band.fill.solid()
    band.fill.fore_color.rgb = PRGB(0x5B, 0x4B, 0xC4)
    band.line.fill.background()
    tf = band.text_frame
    tf.margin_left = PInches(0.5)
    tf.margin_top = PInches(0.18)
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = title
    run.font.size = PPt(28)
    run.font.bold = True
    run.font.color.rgb = PRGB(0xFF, 0xFF, 0xFF)
    if subtitle:
        p2 = tf.add_paragraph()
        run2 = p2.add_run()
        run2.text = subtitle
        run2.font.size = PPt(13)
        run2.font.color.rgb = PRGB(0xE6, 0xE1, 0xFF)
    return slide


def _body(slide, lines, top=1.5, size=16, bullet=True, left=0.7, width=11.6):
    box = slide.shapes.add_textbox(PInches(left), PInches(top), PInches(width), PInches(5.4))
    tf = box.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        prefix = "•  " if bullet else ""
        run = p.add_run()
        run.text = prefix + line
        run.font.size = PPt(size)
        run.font.color.rgb = PRGB(0x1F, 0x24, 0x30)
        p.space_after = PPt(10)
    return box


def build_ppt():
    prs = Presentation()
    prs.slide_width = PInches(13.333)
    prs.slide_height = PInches(7.5)

    # 1. Title
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(1, Emu(0), Emu(0), prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = PRGB(0x5B, 0x4B, 0xC4)
    bg.line.fill.background()
    box = s.shapes.add_textbox(PInches(1), PInches(2.2), PInches(11.3), PInches(3.2))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = "DocuQuery"
    r.font.size = PPt(54); r.font.bold = True; r.font.color.rgb = PRGB(0xFF, 0xFF, 0xFF)
    p2 = tf.add_paragraph()
    r2 = p2.add_run(); r2.text = "A Retrieval-Augmented Web Assistant for Scientific Paper PDFs"
    r2.font.size = PPt(22); r2.font.color.rgb = PRGB(0xE6, 0xE1, 0xFF)
    p3 = tf.add_paragraph()
    r3 = p3.add_run(); r3.text = "\nMinor Project  •  [Your Name]  •  [Roll No.]  •  2025–2026"
    r3.font.size = PPt(16); r3.font.color.rgb = PRGB(0xC9, 0xC2, 0xF5)

    # 2. Problem
    s = _slide(prs, "The Problem", "Why does reading research take so long?")
    _body(s, [
        "Research PDFs are long — methods, data, limits are buried deep",
        "Generic AI summaries hide WHERE the answer came from",
        "Readers must manually hunt pages to verify every claim",
        "Students need answers grounded in the paper — not the internet",
    ], size=20)

    # 3. Solution
    s = _slide(prs, "Our Solution — DocuQuery", "Upload → Ask → Verify")
    _body(s, [
        "Upload a research-paper PDF (any length)",
        "Instant structured RESEARCH BRIEF: objective, data, methods, findings, limits",
        "Ask any question — answers come ONLY from the paper",
        "Every claim shows page + section citations (e.g. [p. 26, Data])",
        "Evidence Trail: inspect the exact source excerpts yourself",
    ], size=19)

    # 4. Architecture
    s = _slide(prs, "System Architecture", "Three clean layers")
    _body(s, [
        "FRONTEND — HTML/CSS/JS + Bootstrap: workspace, auth, summaries, profile",
        "BACKEND (Flask) — 30+ REST APIs: auth & tokens, upload pipeline, RAG Q&A, downloads",
        "INTELLIGENCE — RAG service + Groq LLM + extractive fallback + embeddings",
        "DATA — Supabase PostgreSQL + pgvector (cloud) / SQLite (local demo mode)",
    ], size=19)

    # 5. RAG pipeline
    s = _slide(prs, "How It Works — RAG Pipeline", "Retrieval-Augmented Generation")
    _body(s, [
        "1️⃣  Extract text page-by-page (pypdf) + scientific section detection",
        "2️⃣  Split into overlapping passages (~1,250 chars)",
        "3️⃣  Embed each passage → 384-d vectors (feature hashing / MiniLM)",
        "4️⃣  Store in pgvector — HNSW indexed cosine search",
        "5️⃣  Retrieve top-k relevant passages for the question",
        "6️⃣  Groq LLM answers FROM those passages only, with [p. N] citations",
    ], size=18)

    # 6. Features
    s = _slide(prs, "Key Features", "Complete web application")
    _body(s, [
        "🔐 Auth: register/login, Google Sign-In, password reset, secure tokens",
        "📄 Upload & index PDFs (up to 20 MB, multi-page)",
        "📝 Research Brief + Evidence Trail with page citations",
        "💬 Ask This Paper — grounded Q&A chat",
        "📚 Paper Library — reopen & delete papers",
        "📥 Download briefs (.md / .txt / .json)",
        "👤 Profile: files, password change, Clear History",
    ], size=17)

    # 7. Tech stack
    s = _slide(prs, "Technology Stack", "100% free & open-source")
    _body(s, [
        "Python + Flask — backend & REST API",
        "HTML5, CSS3, JavaScript, Bootstrap 5 — frontend",
        "pypdf — PDF parsing  •  Groq (Llama/GPT-OSS) — LLM",
        "Supabase PostgreSQL + pgvector — cloud database & vector search",
        "pytest (33 tests) + Puppeteer browser tests — quality",
    ], size=19)

    # 8. Demo highlights
    s = _slide(prs, "Live Demo Highlights", "Tested with real data")
    _body(s, [
        "144-page survey paper → 887 passages indexed in ~10 seconds",
        "Q: “What is pre-training?” → grounded answer citing [p. 26, Data]",
        "Works in normal tabs AND sandboxed preview iframes",
        "Multi-user: each account has an isolated library",
        "Runs WITHOUT any API key (extractive preview mode)",
    ], size=19)

    # 9. Testing
    s = _slide(prs, "Testing & Quality", "Verified end-to-end")
    _body(s, [
        "33/33 automated pytest cases — auth, repository, PDF, embeddings, API",
        "Browser tests (headless Chrome): 9/9 — register → upload → ask → clear",
        "Cross-environment: tab / iframe / sandboxed iframe sign-in flows",
        "Edge cases: invalid PDFs, oversized files, bad tokens, rate limits",
    ], size=19)

    # 10. Future scope
    s = _slide(prs, "Future Scope", "Where this goes next")
    _body(s, [
        "OCR for scanned PDFs",
        "Multi-paper comparison Q&A",
        "PDF export & BibTeX citation generator",
        "Email-based password reset",
        "Retrieval quality evaluation + reranking",
        "Cloud deployment (gunicorn + monitoring)",
    ], size=19)

    # 11. Thank you
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(1, Emu(0), Emu(0), prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = PRGB(0x5B, 0x4B, 0xC4)
    bg.line.fill.background()
    box = s.shapes.add_textbox(PInches(1), PInches(2.6), PInches(11.3), PInches(2.4))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run(); r.text = "Thank You!"
    r.font.size = PPt(54); r.font.bold = True; r.font.color.rgb = PRGB(0xFF, 0xFF, 0xFF)
    p2 = tf.add_paragraph()
    r2 = p2.add_run(); r2.text = "\nQuestions & Discussion  •  github.com/Vishal-oly/DocuQuery"
    r2.font.size = PPt(18); r2.font.color.rgb = PRGB(0xE6, 0xE1, 0xFF)

    out = DOCS / "DocuQuery_Presentation.pptx"
    prs.save(out)
    print("slides  ->", out)


if __name__ == "__main__":
    DOCS.mkdir(exist_ok=True)
    build_report()
    build_ppt()
