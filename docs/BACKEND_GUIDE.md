# DocuQuery — Backend Guide (Shivam & Vishal ke liye)

Ye document Flask backend ka poora code samjhaata hai — har file, har pipeline,
har endpoint. Padhne ke baad koi bhi bina code khole backend explain kar sakta
hai. Code snippets actual files se liye gaye hain.

**Backend ka ghar:** `docuquery/` (Python package)
**Total:** 11 files, ~2,250 lines

---

## 1. Big Picture — request ka safar

```
Browser ──HTTP──► routes.py (Flask Blueprint, /api/*)
                     │
                     ├─ auth check: token (header / ?token= / cookie)
                     │
                     ├─ services (business logic):
                     │     pdf_processing.py  PDF → clean chunks
                     │     embeddings.py      text → 384-d vectors
                     │     rag.py             retrieval + summary + Q&A
                     │     llm.py             Groq API calls
                     │
                     ├─ repository.py   data layer (Supabase pgvector / SQLite)
                     ├─ storage.py      PDF file storage (cloud / local)
                     └─ config.py       .env settings
```

**Design rule:** routes sirf HTTP sambhalti hain (validate → call → respond).
Asli kaam services me hai — isliye test karna aasan hai.

---

## 2. File Map

| File | Lines | Kaam |
|---|---|---|
| `__init__.py` | 63 | `create_app()` — Flask app factory + embedded-iframe CORS headers |
| `config.py` | 86 | `.env` loading (dotenv + manual fallback) + `Config` class |
| `routes.py` | 754 | **Saare endpoints** + auth/token system |
| `pdf_processing.py` | 197 | PDF bytes → title + page-wise chunks |
| `embeddings.py` | 81 | Text → 384-dim vectors (hashing / MiniLM) |
| `rag.py` | 238 | Retrieval-Augmented Generation core |
| `llm.py` | 126 | Groq client + error classification + JSON parsing |
| `repository.py` | 518 | Database layer (Supabase + SQLite fallback) |
| `storage.py` | 146 | Uploaded PDF file storage |
| `google_auth.py` | 44 | Google ID-token verification |
| `run.py` (root) | 4 | `create_app().run()` — entry point |

---

## 3. `config.py` — settings ka source

```python
try:
    from dotenv import load_dotenv
    load_dotenv()                  # agar python-dotenv installed hai
except ImportError:
    pass

def _load_env_file(path=None) -> None:
    """Fallback: .env manually padho (BOM-safe), sirf missing vars bharo."""
    ...
_load_env_file()
```

**Do-layer loading** — ye deliberate hai: agar `python-dotenv` missing bhi ho
toh app `.env` padh le (manual parser). Ye parser **kabhi existing env var
override nahi karta** — shell ka value hamesha jeetega.

`Config` class ke important fields:

| Field | Env var | Default | Matlab |
|---|---|---|---|
| `SECRET_KEY` | `FLASK_SECRET_KEY` | local-demo-key | Token signing + session |
| `GROQ_API_KEY` | `GROQ_API_KEY` | `""` | AI on/off isi se decide hota hai |
| `GROQ_MODEL` | `GROQ_MODEL` | `openai/gpt-oss-20b` | Kaunsa model |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | same | `""` | DB connection; khali = SQLite mode |
| `MAX_CONTENT_LENGTH` | `MAX_UPLOAD_MB` (50) | 50 MB | Upload size limit (Flask khud 413 deta hai) |

Health check (`/api/health`) exactly yahi values expose karta hai — debugging
ka first stop.

---

## 4. Auth system (`routes.py`) — samajhne layak dil

### 4.1 Tokens

```python
def issue_token(user_id):        # signed token, 8 ghante valid
    return URLSafeTimedSerializer(SECRET_KEY, salt="docuquery-auth-token").dumps({"uid": user_id})

def verify_token(token):         # invalid/expired → None
    data = serializer.loads(token, max_age=TOKEN_MAX_AGE_SECONDS)
```

Token me data chhupa nahi hota — sirf `uid` hota hai; signature SECRET_KEY se
hoti hai, isliye koi token forge nahi kar sakta.

### 4.2 `_current_user()` — teeno sources se user pehchanna

```python
# 1. Authorization: Bearer <token>   (normal API calls)
# 2. ?token=<token>                  (downloads / embedded iframes)
# 3. X-Auth-Token header             (extra fallback)
# aur phir: cookie session (Flask session["user"])
```

Koi token valid mila → user DB se load → cookie session me bhi save (best
effort) → return. Token nahi → `session.get("user")` (cookie wala).

### 4.3 `_session_id()` — data isolation

Har paper/chunk ek `session_id` ke under rehta hai:
- Logged-in user → uska `user["id"]`
- Anonymous → ek random browser session id

**Har query is filter ke saath jaati hai** — isliye kisi aur ka data kisi ko nahi
milta (Supabase me RLS bhi lagaa hai, defense in depth).

### 4.4 Decorators

```python
@api_login_required    # API ke liye → 401 JSON {"error": "Please sign in to continue."}
@page_login_required   # HTML pages ke liye → redirect /login
```

---

## 5. Endpoints — poora list

### Pages (HTML)

| Route | Function | Notes |
|---|---|---|
| `GET /` | `home_page` | landing.html |
| `GET /login` | `login_page` | login.html (+ google_client_id context) |
| `GET /forgot` | `forgot_page` | reset flow |
| `GET /workspace` | `workspace_page` | login required |
| `GET /summaries`, `GET /profile` | — | login required |

### Auth APIs

| Endpoint | Kya karta hai |
|---|---|
| `POST /api/register` | `_validate_credentials()` → password hash (Werkzeug) → `save_user` → 201 + token |
| `POST /api/login` | email se user → `check_password_hash` → token issue |
| `POST /api/auth/google` | Google ID token verify (`google_auth.py`) → login/register auto |
| `POST /api/logout` | session clear |
| `GET /api/me` / `PATCH /api/me` | profile read / name update |
| `POST /api/me/password` | current password check → new hash |
| `POST /api/forgot` / `POST /api/reset` | reset code issue → new password set |
| `POST /api/me/clear-history` | user ke saare papers + chunks + chats delete (`{"deleted": N}`) |
| `GET /api/health` | mode report (DB backend, llm_available, model, max_upload_mb) |

### Papers APIs (sab login-required)

| Endpoint | Kya karta hai |
|---|---|
| `GET /api/papers` | User ki papers list (newest first) |
| `GET /api/papers/<id>` | Ek paper + uska summary |
| `POST /api/upload` | **Main pipeline** (neeche detail me) |
| `POST /api/papers/<id>/ask` | **Q&A pipeline** (neeche detail me) |
| `DELETE /api/papers/<id>` | Paper + chunks + stored file delete |
| `GET /api/papers/<id>/file` | Original PDF stream (`storage.read`) |
| `GET /api/papers/<id>/download?format=` | Brief as `.md` / `.txt` / `.json` (unknown format → 400) |
| `POST /api/papers/<id>/summarize` | Brief dobara generate (manual trigger) |

---

## 6. Upload pipeline — `POST /api/upload` (sabse important)

```
routes.upload_pdf()                          ← routes.py:480
 1. file check: "pdf" field? .pdf extension?  → 400 "Only PDF files are supported."
 2. parse_pdf_bytes(raw, filename)            → title, page_count, chunks[]
        har chunk: { page_number, section, content }
 3. embedder.embed([chunk contents])          → 384-d vector per chunk
 4. storage.save(paper_id, filename, raw)     → file save (agar fail → warning, flow nahi rukta)
 5. paper dict banao (id, session_id, title, page_count, summary:{} ...)
 6. chunk rows banao (id, paper_id, session_id, page_number, section, content, embedding)
 7. repository.save_paper() + save_chunks()
 8. make_summary(...)                         → brief (AI ya extractive)
 9. repository.update_summary()               → summary DB me save
10. 201 → { paper, summary, chunk_count, database, text_char_count }
```

**Error contract (yaad rakho):**

| Case | Status | Message |
|---|---|---|
| File nahi / non-PDF | 400 | "Choose a PDF file to upload." / "Only PDF files are supported." |
| Corrupt PDF | 400 | "This file does not look like a valid PDF." (PDFProcessingError se) |
| Password-protected | 400 | "This PDF is password-protected..." |
| Bada file | 413 | Flask ka MAX_CONTENT_LENGTH |
| DB/embedding failure | 503 | RepositoryError / EmbeddingError |
| Baaki sab | 500 | generic + server log |

---

## 7. `pdf_processing.py` — PDF se nikalne ka kaam

```
parse_pdf_bytes(raw, filename)
  ├─ pypdf se page-wise text nikalo (encrypted → PDFProcessingError)
  ├─ _sanitize_text(): control characters hatao, whitespace normalise
  ├─ _split_sections(): Abstract / Introduction / Methods / Results headings
  │      detect karke chunks ko section tag do (fallback: "Overview")
  ├─ _chunk_text(): 1,250 characters ke chunks, 180 ka overlap
  │      (overlap isliye ki boundary par answer cut na ho)
  └─ _guess_title(): pehle page se title, warna filename
```

**Tested behaviour (yaad rakho):** 1-page sample → 7 chunks | 144-page survey
→ 887 chunks in ~10 s. Scanned PDF (no text layer) → upload succeed hota hai
par brief me OCR notice aata hai.

---

## 8. `embeddings.py` — text ko numbers banana

| Backend | Kab | Kaise |
|---|---|---|
| `HashingEmbedder` (default) | hamesha chalta hai | Feature hashing → 384-d vector. Zero dependencies |
| `SentenceTransformerEmbedder` | optional (`EMBEDDING_BACKEND`, `requirements-embeddings.txt`) | MiniLM — semantic, 384-d, normalized |

`make_embedder(backend, model_name)` decide karta hai. **Why hashing default?**
Demo machine par heavy ML model install karna na pade — aur honest mode naming
me dikhta hai ("hashing") jo health endpoint me bhi report hota hai.

---

## 9. `rag.py` — RAG ka dil (samajhne laayak!)

### 9.1 Retrieval

```python
def retrieve_summary_chunks(repository, embedder, session_id, paper_id, fallback_chunks, top_k=2):
    vector = embedder.embed([query])[0]
    return repository.search_chunks(session_id, paper_id, vector, top_k)
    # DB me: cosine similarity, pgvector HNSW index
```

Question → embedding → DB similarity search → top-k passages.

### 9.2 `format_context()` — LLM ko dene wala "open-book"

Retrieved chunks ko ek text block me arrange karta hai with page/section labels,
taaki LLM jawab ke saath `[p. N]` cite kar sake. Cap: 18,000 characters.

### 9.3 `make_summary()` — brief generation

```
make_summary(...)
  ├─ retrieve_summary_chunks(top_k=2)     → paper ke most relevant parts
  ├─ GROQ_API_KEY hai?
  │     HAAN → generate_structured_summary()  → objective/dataset/methodology/
  │              key_findings/limitations/conclusion/overall_summary (JSON)
  │     NAHI → extractive_summary()  → paper ki apni best sentences quote karo
  └─ modes: "Groq RAG"  |  "extractive preview"   (UI me badge banti hai)
```

**Failure par honesty:** agar Groq call fail ho jaaye toh summary notice me
specific reason aata hai (e.g. "GROQ_API_KEY is not set", "rate limit reached
(free tier: 30 requests/minute)") — ye `llm.py` ki classification se aata hai.
Kabhi bhi silent fallback nahi hota.

### 9.4 `answer_question()` — anti-hallucination wala hissa

```python
def answer_question(repository, embedder, config, session_id, paper, question):
    vector = embedder.embed([question])[0]
    chunks = repository.search_chunks(...)      # top-k passages
    if not relevant chunks:
        return { "answer": "no matching passages found in this paper", "mode": "no-match", ... }
    context = format_context(chunks)
    answer = answer_from_context(question, context, api_key, model)
    return { "answer": answer, "sources": citation_sources(chunks), "mode": "Groq RAG" }
```

LLM ka system prompt kehta hai: **"sirf diye context se jawab do; agar context
me jawab na ho toh bolo ki paper me iska jawab nahi hai."** Isi liye kabhi-kabhi
AI bolti hai "the paper does not cover this" — ye **feature** hai, bug nahi.
Interview me ye sabse strong point hai.

`citation_sources(chunks)` — UI ki Evidence Trail ke liye {page_number,
section, excerpt} list.

`extractive_summary(chunks)` — offline mode: `_best_extract()` sentences ki
scoring (position, section, length) se paper ki apni lines choose karta hai.

---

## 10. `llm.py` — Groq client

```python
def _call_groq(api_key, model, messages, max_tokens=1400):
    if not api_key:
        raise LLMError("Groq API key is not configured — add GROQ_API_KEY to your .env file and restart.")
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        ...
    except ...:
        # errors ko classify karta hai:
        #  401 → "invalid or revoked"
        #  429 → "rate limit reached (free tier: 30 requests/minute)"
        #  network → "could not be reached — check your internet connection"
        #  empty content → "Groq returned an empty response."
```

| Function | Kaam |
|---|---|
| `generate_structured_summary(context, ...)` | Prompt bhejta hai jo **strict JSON** return kare; `_parse_json_object()` se parse; fields missing ho toh defaults |
| `answer_from_context(question, context, ...)` | "reading assistant" prompt ke saath grounded answer |

Model: `openai/gpt-oss-20b` (free tier). Note: ye reasoning model hai —
`max_tokens` chhota ho toh `content` empty aa sakta hai (reasoning tokens consume
hote hain); isliye 1400 rakha hai.

---

## 11. `repository.py` — data layer

**Do modes:**

| Mode | Kab | Kaise |
|---|---|---|
| **Supabase pgvector** | `SUPABASE_URL` + service key set ho | REST calls (supabase-py client); vector search SQL/RPC se |
| **SQLite (local)** | env vars khali | file DB (default `instance/docuquery.db`) — offline demo |

Key functions (dono modes ke andar same interface):

```
save_user / get_user_by_email / get_user
save_paper / get_paper / list_papers / delete_paper / update_summary
save_chunks / search_chunks(session_id, paper_id, vector, top_k)   ← cosine similarity
set_reset_token / get_user_by_reset_token
update_user_name / update_user_password
clear_session_data(session_id)    ← clear-history
```

**Schema (`schema/supabase.sql`):**

```sql
users (id, name, email unique, password_hash, created_at)
papers (id, session_id, title, filename, page_count, created_at, summary jsonb)
paper_chunks (id, paper_id → cascade delete, session_id, page_number,
              section, content, embedding vector(384))   + HNSW/cosine index
```

Service-role key **server-side only** — browser kabhi nahi dekhta. RLS enabled
(README/schema me details).

---

## 12. `storage.py` — PDF files kahan rehte hain

```python
class FileStorage:
    def save(paper_id, filename, raw)   # cloud (Supabase Storage bucket "papers") ya local uploads/
    def read(path)                      # GET /api/papers/<id>/file isko stream karta hai
    def delete_paper(paper_id)
```

Upload flow me storage fail ho jaaye toh flow **nahi rukta** (warning log +
`"storage": "skipped"`) — demo kabhi tootta nahi. Read path me auto-repair:
local DB + cloud file ka mix dikhe toh cross-check kar leta hai.

---

## 13. `google_auth.py`

`verify_google_credential(id_token, client_id)` — Google ki ID token verify
karta hai (audience check). Email already hai toh usi account me sign-in; naya
email → auto register (password random rehta hai). `GOOGLE_CLIENT_ID` unset ho
toh login page par Google section hi hide ho jaata hai.

---

## 14. Do poori kahaniyan (interview ke liye gold)

### Upload (10 second ki kahani)
> "PDF aata hai → pypdf se page-wise text + section detection → 1,250-char
> chunks (180 overlap) → 384-d embeddings → Supabase pgvector me save (HNSW
> index) → Groq ko retrieved context dekar structured brief banwate hain with
> page citations → agar key na ho toh extractive preview honestly label hota
> hai. 144-page paper: 887 chunks, ~10 seconds."

### Ask (10 second ki kahani)
> "Question embed hota hai → cosine similarity se top passages milte hain →
> wo passages ek 'open-book context' ban kar Groq ko jaate hain → model sirf
> usi context se jawab deta hai with `[p. N]` citations → agar paper me jawab
> na ho toh wo bolti hai 'paper does not cover this' — hallucination control
> ka ye main mechanism hai."

---

## 15. Common questions (backend)

| Q | A |
|---|---|
| Hallucination kaise rokte ho? | Grounded context-only prompting + page citations + honest refusal; har claim Evidence Trail se verify ho sakti hai |
| SQLite mode kyun? | Credential-free demo fallback (offline bhi chalta hai) |
| Password kahan hai? | `password_hash` (Werkzeug scrypt) — plain text kabhi nahi |
| Service key safe kaise? | Sirf server `.env` me; `.gitignore` me; zip me bhi wahi file hai jo local run ke liye hai |
| Rate limit? | Groq free tier 30 RPM / 8K TPM / 1,000 req/day — 429 par friendly message |
| Embeddings default kyun hashing? | Zero-dependency demo; MiniLM optional upgrade (health endpoint honestly report karta hai) |
| Tests? | 42 pytest cases: auth, repository, RAG, PDF parsing, API contracts, error classification |

---

## 16. Debugging tips (jab kuch tootte hai)

1. **Pehle `GET /api/health`** — `database` (Supabase/SQLite), `llm_available`,
   `embedding_backend`, `max_upload_mb` — aadhi problems yahin se dikhti hain.
2. **"Groq API key is not configured"** → `.env` me key + server restart.
   Message me specific cause hota hai — usko follow karo.
3. **503 aaye** → repository/embedding layer — server log dekho (Flask console).
4. **Upload 400** → PDFProcessingError ka message UI me jaata hai waise waise.
5. Tests chalao: `python -m pytest -q` (42 passing) — koi bhi change ke baad
   ye sabse fast check hai.

---

*Ye guide current code (commit `bfaca1c`+) par based hai. Sabse pehle
`routes.py` ka upload + ask section padh lo — backend ka 60% wahi hai.*
