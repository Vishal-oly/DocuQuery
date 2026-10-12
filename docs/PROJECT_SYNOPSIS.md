# Minor Project Synopsis — DocuQuery

## Project title

**DocuQuery: A Retrieval-Augmented Web Assistant for Scientific Paper PDFs**

## Abstract

Scientific papers contain detailed methods, results, and limitations that can be difficult to find quickly. DocuQuery is a web-based reading assistant that accepts a research-paper PDF, extracts text page by page, separates it into searchable passages, and retrieves evidence relevant to a structured research brief or a user's question. The workspace presents the brief alongside page-linked excerpts so readers can inspect the source. The interface is built with HTML, CSS, JavaScript, and Bootstrap; the backend uses Python and Flask. Groq provides optional language-model generation, while Supabase PostgreSQL with pgvector is the configured persistent store. A local SQLite mode and extractive preview support a demonstration without external credentials.

## Problem statement

Reading a full research article is time-consuming, and short generic summaries may hide the methodology, data, limitations, or evidence behind a claim. Readers also need to locate the source passage that supports an answer. DocuQuery addresses these needs by combining retrieval with structured generation and displaying page and section references with the results.

## Objectives

1. Accept and validate scientific-paper PDF uploads.
2. Extract selectable PDF text while preserving page numbers.
3. Detect common scientific-paper sections and split text into overlapping passages.
4. Create 384-dimensional passage vectors using offline feature hashing or optional MiniLM.
5. Store paper metadata, summaries, passages, and vectors in Supabase/pgvector or local SQLite.
6. Retrieve relevant evidence for summary fields and user questions.
7. Generate a structured research brief and grounded answers with Groq when configured.
8. Display source excerpts and page references in a responsive, accessible workspace.

## Scope

The current prototype focuses on selectable text in journal-style PDFs. It provides a single-page workspace with PDF upload, a paper library for the current browser session, a research brief, an evidence trail, and question answering. It does not include user accounts, OCR, or guaranteed extraction of complex tables, figures, equations, and multi-column layouts. It is intended as a student minor-project prototype and a reading aid, not as a replacement for checking the source article.

## Proposed workflow

```text
Research PDF
   ↓
File validation and page-wise text extraction
   ↓
Scientific-section detection and overlapping chunking
   ↓
384-dimensional vectors (feature hashing; optional MiniLM)
   ↓
Supabase pgvector or local SQLite storage
   ↓
Relevant page- and section-linked passage retrieval
   ↓
Groq structured brief / grounded answer
   ↓
Research brief, answer, and evidence trail in the DocuQuery workspace
```

## Main modules

- **Web workspace:** PDF upload, research brief, evidence trail, paper chat, and session paper library.
- **Flask routes:** health status, upload, paper list/load/delete, and question-answer API.
- **PDF processor:** file validation, page extraction, section detection, and chunk creation.
- **Embedding adapter:** deterministic offline feature hashing by default; optional Sentence Transformers MiniLM.
- **Repository layer:** Supabase/pgvector persistence with a local SQLite development fallback.
- **RAG service:** relevant-passage retrieval, structured-summary context, answer context, and citation formatting.
- **Groq adapter:** structured research briefs and source-grounded answers; a clearly labelled extractive/retrieval preview works without a Groq key.

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, JavaScript, Bootstrap 5 |
| Backend | Python, Flask |
| PDF processing | pypdf |
| Text embeddings | Feature hashing; optional Sentence Transformers MiniLM |
| Vector database | Supabase PostgreSQL + pgvector |
| Local development store | SQLite |
| Language model | Groq Chat Completions |
| Testing | pytest, Flask test client |

## Testing plan

- Confirm deterministic, normalized embedding vectors.
- Test section detection, page-aware chunk creation, and overlap boundaries.
- Reject invalid/non-PDF uploads and enforce the configured upload limit.
- Test local-storage ranking, paper/session isolation, and deletion.
- Smoke-test the web workspace, health endpoint, PDF upload, research brief, and Q&A endpoints.
- When configured, run an end-to-end check against a Supabase project and Groq API key.

## Expected outcome

A reader can upload or reopen a scientific paper, receive a structured brief, inspect page-linked evidence, ask a follow-up question, and revisit papers in the same browser session. Supabase offers managed persistent storage when configured; the SQLite mode supports a local demonstration. The included synthetic sample PDF can be used to test the main flow without relying on a real publication.

## Limitations and future improvements

- Add OCR for scanned PDFs and improve extraction for tables, figures, equations, and multi-column text.
- Evaluate retrieval quality on a labelled set of papers and questions; compare feature hashing with MiniLM and add reranking if useful.
- Add authentication and per-user access controls before public deployment.
- Add multi-paper comparison, citation export, and downloadable brief reports.
- Treat model-generated content as assistance only and verify claims against the original source.
