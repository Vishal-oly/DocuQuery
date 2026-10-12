# DocuQuery — Complete Workflow Explanation

> Reference: `docs/NAVIGATION_DIAGRAM.*` (target design) + actual implementation in `docuquery/`
> Note: the navigation diagram shows the *aspirational* design (Login/Auth/Profile). The current
> prototype runs **without accounts** — papers are scoped to a random browser-session ID. Both
> views are described below.

---

## 1. High-level data pipeline (core of the project)

```text
Research PDF
   │
   ▼
[Flask Upload + Validation]  ── .pdf check, %PDF magic bytes, 20 MB limit
   │
   ▼
[PyPDF page-wise text extraction]  ── page numbers preserved
   │
   ▼
[Scientific section detection]  ── Abstract / Intro / Methods / Data / Results / ...
   │
   ▼
[Overlapping chunking]  ── 1250 chars, 180 overlap, sentence-boundary aware
   │
   ▼
[Embeddings: 384-dim]  ── feature hashing (default, offline) OR MiniLM (optional)
   │
   ▼
[Storage]  ── Supabase PostgreSQL + pgvector  (or local SQLite demo mode)
   │
   ▼
[Retrieval]  ── cosine similarity, page + section linked passages
   │
   ▼
[Groq LLM]  ── structured research brief / grounded answer (extractive fallback without key)
   │
   ▼
[Workspace UI]  ── Research Brief + Evidence Trail + Ask This Paper
```

---

## 2. App startup workflow

```text
python run.py
  → create_app()                       (docuquery/__init__.py)
  → load Config from .env               (config.py)
  → Repository(config)                 (repository.py)
        ├─ SUPABASE_URL + SERVICE_ROLE_KEY set → Supabase pgvector mode
        └─ otherwise                       → local SQLite (instance/demo.sqlite3)
  → make_embedder()                    (embeddings.py)
        ├─ EMBEDDING_BACKEND=hashing               → deterministic feature hashing
        └─ EMBEDDING_BACKEND=sentence-transformers → MiniLM (all-MiniLM-L6-v2)
  → register Blueprint (routes.py)
  → Flask listens on 0.0.0.0:5000
```

---

## 3. Session / Home workflow (browser entry)

```text
User opens http://127.0.0.1:5000
  → GET /  → guest Home page (landing.html)
        Project name & about, features, How-it-works, Login / Register buttons, navigation menu
  → GET /login  → Login / Register page (login.html)
        Enter credentials or create account → validate input → POST /api/login or /api/register
        Successful login → /workspace (Dashboard)
        Forgot password: optional stub
  → GET /workspace (requires login; redirects to /login otherwise)
  → renders single-page workspace (templates/index.html)
  → app.js initialize()
        ├─ GET /api/health   → header chips: DB mode, LLM status, embedding backend, upload limit
        └─ GET /api/papers   → Paper Library (papers saved to this account)
  → Logout button → POST /api/logout → back to guest Home page
```

**Authentication workflow (current code):**
- `POST /api/register` — name/email/password validated, password hashed (werkzeug),
  account saved to `users` table (SQLite or Supabase), auto sign-in.
- `POST /api/login` — email + password check → sign-in.
- Session cookie carries the signed-in user; papers are scoped to the account id,
  so a user's papers survive logout/login and new browsers.
- `GET /api/me` / `POST /api/logout` — current user and sign-out.
- Paper APIs (`/api/papers*`, `/api/upload`) require sign-in (401 JSON otherwise).

---

## 4. Upload + ingestion workflow (POST /api/upload)

```text
User: drag-drop or browse a PDF  (app.js uploadFile)
  │
  ▼
POST /api/upload  (multipart field: "pdf")
  │
  ├─ Validate: file present? secure_filename? ends with .pdf?
  ├─ parse_pdf_bytes()                     (pdf_processing.py)
  │     ├─ reject non-%PDF bytes, encrypted PDFs, 0-page PDFs
  │     ├─ extract text page by page (pypdf) — page numbers kept
  │     ├─ _split_sections(): heading rules → Abstract/Introduction/Methods/
  │     │                    Data/Results/Discussion/Limitations/Conclusion/References
  │     ├─ _chunk_text(): 1250-char chunks, 180 overlap, split at sentence boundaries
  │     ├─ _guess_title() from first page
  │     └─ fail clearly if no selectable text (scanned PDF → needs OCR, not included)
  │
  ├─ embedder.embed(all chunk texts) → 384-dim vector per chunk
  │
  ├─ repository.save_paper()   → papers table  (id, session_id, title, filename, page_count, created_at)
  ├─ repository.save_chunks()  → paper_chunks  (page_number, section, content, embedding)
  │
  ├─ rag.make_summary()
  │     ├─ retrieve_summary_chunks(): 6 fixed research questions
  │     │      (objective/method/dataset/results/limitations/conclusion)
  │     │      → each question embedded → vector search top-2 → merged unique passages
  │     ├─ format_context(): "[Source: file | p.N | Section]" blocks, ≤18k chars
  │     ├─ Groq generate_structured_summary() → fields:
  │     │      overall_summary, objective, methodology, dataset,
  │     │      key_findings, limitations, conclusion
  │     └─ if Groq unavailable → extractive_summary() fallback
  │            (keyword + section ranked sentences, page-cited, labelled "extractive preview")
  │
  ├─ citation_sources() → Evidence Trail cards {page_number, section, excerpt, similarity}
  ├─ repository.update_summary()  → summary saved with the paper
  │
  ▼
201 JSON { paper, summary, chunk_count, database, text_char_count }
  → UI: Research Brief rendered, Evidence Trail rendered, chat enabled,
        paper added to Library, "Start Processing" status → done
```

---

## 5. Ask This Paper / Chat workflow (POST /api/papers/<id>/ask)

```text
User types a question (≤1200 chars) or clicks a suggested prompt
  │
  ▼
POST /api/papers/<id>/ask   { "question": "..." }
  │
  ├─ session check + paper lookup (must belong to this browser session)
  ├─ embedder.embed(question) → query vector
  ├─ repository.search_chunks(top_k=6)
  │     ├─ Supabase mode: match_paper_chunks() RPC
  │     │      cosine distance (embedding <=> query), HNSW index, session+paper scoped
  │     └─ SQLite mode: cosine similarity computed in Python
  │
  ├─ no matches → "I could not find relevant text..." (mode: no matching passages)
  │
  ├─ format_context(chunks, 12000 chars) with page/section headers
  ├─ Groq answer_from_context(question, context)
  │      → grounded answer, instructed to use only retrieved text, cite pages
  └─ Groq fails → retrieval preview: top-2 raw excerpts with [p. N] quotes
  │
  ▼
{ answer, mode: "Groq RAG" | "retrieval preview", sources[] }
  → chat bubble + Evidence Trail source cards
```

---

## 6. Paper Library / Reopen / Delete workflow

```text
GET    /api/papers          → list session papers (newest first)
Click  a library item       → GET /api/papers/<id> → saved summary + paper meta loaded
DELETE /api/papers/<id>     → paper + chunks removed (FK ON DELETE CASCADE)
```

---

## 7. Storage layer workflow

```text
                    ┌────────────────────────────────────────────┐
                    │              Repository layer               │
                    │            (repository.py)                  │
                    └───────────┬──────────────────┬─────────────┘
                                │                  │
                  SUPABASE creds present        no creds
                                │                  │
                                ▼                  ▼
                 Supabase PostgreSQL+pgvector   Local SQLite
                 ─────────────────────────     ──────────────
                 papers (metadata + summary    same tables,
                         jsonb)                embeddings as text,
                 paper_chunks (content +        cosine in Python
                         vector(384))
                 match_paper_chunks RPC
                 (cosine, HNSW index)
                 RLS ON — service-role only
                 (key never sent to browser)
```

**Tables (schema/supabase.sql):**
- `papers(id, session_id, title, filename, page_count, created_at, summary jsonb)`
- `paper_chunks(id, paper_id FK cascade, session_id, page_number, section, content, embedding vector(384))`
- `match_paper_chunks(query_embedding, session_id, paper_id, match_count)` → similarity-ranked rows

---

## 8. Target navigation flow (from the diagram) vs current code

| Diagram (target design) | Current implementation |
|---|---|
| Home (Guest) → Login / Register | ✅ Guest Home (`/`) → Login/Register (`/login`) |
| Supabase Auth (email/password, accounts) | ✅ Email/password accounts (`users` table, hashed passwords; works in SQLite & Supabase modes) |
| Nav bar: Home \| Upload \| Chat/Ask \| Summaries \| Profile \| Logout | ✅ Workspace nav + Summaries + Profile + user chip & Logout |
| Summaries page + Download | ✅ `/summaries` — view brief, regenerate, download (.md/.txt/.json), view document |
| Profile page (details, files, settings) | ✅ `/profile` — user details, change password, uploaded files, app settings |
| Logout → end session | ✅ Logout button ends the session and returns to Home |
| Store uploaded files (Storage) | ✅ Local `instance/uploads/` (+ optional Supabase Storage sync) with View Document |
| Forgot password (optional) | ✅ `/forgot` — demo reset-code flow |
| Vector DB + Backend Processing + Groq LLM + Supabase Storage | ✅ Same in code: embeddings, repository, rag, llm modules |

**Future work:** Supabase Auth (managed identity) upgrade, email delivery for password reset,
downloadable PDF brief reports, OCR for scanned PDFs.

---

## 9. API summary

| Method | Route | Workflow |
|---|---|---|
| GET | `/` | Guest Home page (about, features, Login/Register) |
| GET | `/login` | Login / Register page (redirects to workspace if signed in) |
| GET | `/workspace` | Research workspace SPA (requires sign-in) |
| POST | `/api/register` | Create account → auto sign-in |
| POST | `/api/login` | Sign in with email/password |
| POST | `/api/logout` | End the session |
| GET | `/api/me` | Current signed-in user |
| GET | `/api/health` | DB mode, LLM availability, embedding backend, upload limit |
| GET | `/api/papers` | Paper library list (requires sign-in) |
| GET | `/api/papers/<id>` | Reopen paper + saved brief (requires sign-in) |
| POST | `/api/upload` | Validate → extract → chunk → embed → store → brief (requires sign-in) |
| POST | `/api/papers/<id>/ask` | Embed question → retrieve → Groq answer + sources (requires sign-in) |
| DELETE | `/api/papers/<id>` | Remove paper and its chunks (requires sign-in) |

## 10. Error / fallback workflows (defensive paths)

- Non-PDF / corrupt / encrypted / empty PDF → 400 with clear message
- File > 20 MB → 413 from Flask app factory handler
- Scanned PDF (no text) → 400 "OCR support is not enabled"
- No Supabase creds → automatic SQLite demo mode (nothing breaks)
- No GROQ_API_KEY / Groq error → labelled **extractive preview** summary & **retrieval preview** answers
- Question > 1200 chars → 400
- Wrong session / missing paper → 404
