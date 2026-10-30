# DocuQuery — Backend Technology Choices
### Har cheez: KYU use kiya · KAHAN hai · KYA CHANGES ho sakte hain · KYA FAYADA hai

Ye doc interview ke liye perfect hai — jab sir poochein *"ye kyun use kiya?"*
toh yahan se 30-second me jawab ready hai.

---

## 1. Flask (Web Framework)

### Kyu use kiya?
- Python ka **lightweight** framework — sirf wahi deta hai jo chahiye (routes,
  request handling), bloat nahi.
- **App factory pattern** (`create_app()`) easily support karta hai — testing
  me alag-alag configs bana kar test karna aasan.
- Seekhna chhota hai, project ke size ke liye perfect — Django jaisa heavy
  framework is project par overkill hota.

### Kahan hai?
- `run.py` → `create_app()` call
- `docuquery/__init__.py` → app factory (blueprint register, CORS)
- `docuquery/routes.py` → saare endpoints (754 lines, ek blueprint)

### Kya changes kar sakte hain?
- **FastAPI** me migrate kar sakte hain (agar async + auto-docs chahiye) —
  trade-off: naya seekhna padega, aur small project me fayda kam.
- **Blueprints** ko modules me tod sakte hain (auth_routes.py, paper_routes.py)
  — project bade hone par code organize rehta hai.
- **Flask-Limiter** laga sakte hain rate limiting ke liye (package #3 idea).
- Debug mode off hi rehne do production me (abhi bhi off hai ✅).

### Fayada?
- Kam dependencies = kam security surface + fast startup
- Tests simple hain (test client built-in)
- Koi async complexity nahi — synchronous, predictable flow

---

## 2. Supabase PostgreSQL + pgvector (Database + Vector Search)

### Kyu use kiya?
- **Free managed PostgreSQL** — khud server maintain nahi karna padta.
- **pgvector extension** = vector search DATABASE ke andar hi — alag se
  Pinecone/Weaviate jaisa paid vector DB ki zarurat nahi.
- **HNSW index** pgvector me milta hai — 887 chunks par search milliseconds me.
- **RLS (Row-Level Security)** built-in — data isolation DB level par.

### Kahan hai?
- `docuquery/repository.py` — saari queries (518 lines): `save_paper`,
  `search_chunks` (cosine similarity), `list_papers`...
- `schema/supabase.sql` — tables: `users`, `papers`, `paper_chunks` with
  `embedding vector(384)` + HNSW cosine index
- Config: `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (`.env` me)

### Kya changes kar sakte hain?
- **Embedding dimension** badal sakte hain (schema me `vector(384)` → jaise
  MiniLM-384 hai, agar bada model lo toh `vector(768)` karna padega + index
  rebuild)
- **Index type**: HNSW → IVFFlat (bahut bade datasets par memory bachti hai)
- **Full-text search** bhi add kar sakte hain (Postgres `tsvector`) — hybrid
  search (vector + keyword) best hota hai research papers ke liye.
- **Supabase Auth** use kar sakte hain khud ke auth ki jagah (trade-off: kam
  control, kam code).
- Connection pooling (Supabase pooler URL) for scale.

### Fayada?
- Vector + relational data **ek hi jagah** — consistency + ek hi backup
- Free tier project ke liye kaafi (1 GB DB + 5 GB storage)
- RLS = DB level security (app-level bugs par bhi data safe)

---

## 3. RAG Pattern (Retrieval-Augmented Generation)

### Kyu use kiya?
- Seedha LLM se poochne par wo **general knowledge** se jawab deta hai —
  hallucination hota hai, page references nahi hote.
- RAG me pehle **paper ke actual passages** retrieve hote hain, phir LLM sirf
  unhi se jawab deta hai → **grounded + verifiable** answers.
- Is project ka core USP yahi hai: *"Evidence You Can Verify"* — page citations.

### Kahan hai?
- `docuquery/rag.py` (238 lines) — poora pipeline:
  - `retrieve_summary_chunks()` — top-k passages
  - `format_context()` — "open-book" banana (18K char cap)
  - `make_summary()` — brief generation (AI + extractive dono)
  - `answer_question()` — Q&A with honest refusal
  - `citation_sources()` — Evidence Trail
- `llm.py` — actual Groq calls (`answer_from_context`, `generate_structured_summary`)

### Kya changes kar sakte hain?
- **top_k** tune kar sakte hain (abhi 2 for summary, zyada for Q&A → better
  recall, zyada tokens)
- **Hybrid search**: vector + keyword (BM25) — technical papers me exact terms
  ke liye better
- **Reranking**: pehle 20 passages lo, phir cross-encoder se top-5 chuno —
  quality upar, cost thoda upar
- **Conversation memory**: chat ka context carry karna (abhi har question
  independent hai)
- **Citation verification**: answer ke `[p. N]` ko automatically check karna
  ki page me wahi hai ya nahi

### Fayada?
- Hallucination **control** (poori tarah se eliminate mushkil, but grounded
  + honest refusal se near-zero)
- Har claim **verifiable** — page number + excerpt
- Model ka knowledge cutoff matter nahi karta — answer hamesha uploaded paper se

---

## 4. Groq API + `openai/gpt-oss-20b` (LLM)

### Kyu use kiya?
- **Free tier** — 30 requests/minute, 1,000 requests/day — demo/college ke
  liye kaafi.
- **Ultra-low latency** — Groq ka LPU inference fast hai (2-4 second me jawab).
- `gpt-oss-20b` — open-source reasoning model, structured JSON output deta hai
  (brief ke liye perfect).

### Kahan hai?
- `docuquery/llm.py` (126 lines):
  - `_call_groq()` — client + **error classification** (missing key / 429 /
    401 / network — sab ke specific messages)
  - `generate_structured_summary()` — strict-JSON prompt + `_parse_json_object()`
  - `answer_from_context()` — "reading assistant" system prompt
- Config: `GROQ_API_KEY`, `GROQ_MODEL` (`.env` me)

### Kya changes kar sakte hain?
- **Model swap**: `GROQ_MODEL` badal do — Llama-3.3-70B (zyada capable) ya
  koi chhota model (sasta/fast). `.env` me ek line!
- **OpenAI / Gemini / local Ollama** me migrate — `llm.py` ke 2 functions
  change karne honge (`_call_groq` → `_call_openai`), baaki sab same.
- **Temperature** (abhi 0.15) — kam = factual, zyada = creative.
- **max_tokens** (abhi 1400) — reasoning models me chhota rakhoge toh empty
  content aata hai (reasoning tokens consume hote hain) — isliye 1400.
- **Structured output** (JSON mode) agar API support kare toh parsing aur robust.

### Fayada?
- Zero cost (free tier) — project ₹0 me chalta hai
- Fast responses = demo me maza aata hai
- Model configurable hai — koi bhi Groq model daal sakte ho

---

## 5. Embeddings — HashingEmbedder (default) + MiniLM (optional)

### Kyu use kiya?
- Text ko **numbers (vectors)** me badalna zaroori hai — tabhi similarity
  search ho sakti hai ("meaning" ki jagah numbers compare hote hain).
- **Hashing default** isliye: zero dependencies, har machine par chalta hai
  (demo-safe) — bina kisi ML model download ke.
- **MiniLM optional** (384-d sentence-transformers) — semantic search better
  ("car" aur "automobile" same direction me aate hain).

### Kahan hai?
- `docuquery/embeddings.py` (81 lines):
  - `HashingEmbedder` — feature hashing → 384-d
  - `SentenceTransformerEmbedder` — MiniLM (optional install)
  - `make_embedder(backend, model_name)` — factory
- Config: `EMBEDDING_BACKEND` (default: hashing)
- Health endpoint honestly report karta hai kaunsa chal raha hai

### Kya changes kar sakte hain?
- **MiniLM enable karo**: `pip install -r requirements-embeddings.txt` + env
  set — retrieval quality upar.
- **Bigger models** (e.g., bge-base, 768-d) — par schema me `vector(384)` →
  `vector(768)` karna padega + index rebuild.
- **API embeddings** (OpenAI text-embedding-3) — better quality, per-call cost.
- **Dimension reduction** (PCA) agar storage bachani ho.

### Fayada?
- Default mode **har laptop par chalta hai** (college demo me tension nahi)
- Honest labeling — health me dikhta hai "hashing" — koi pretend nahi
- Upgrade path clean hai — sirf factory me switch

---

## 6. SQLite Fallback (Offline Mode)

### Kyu use kiya?
- **Bina internet/credentials ke demo** chal sake — classroom me kabhi WiFi na
  ho toh bhi project dikha sakte ho.
- Supabase down ho ya free-tier pause ho jaaye — backup mode ready.

### Kahan hai?
- `docuquery/repository.py` — same interface, do implementations (Supabase /
  SQLite). Mode auto-select: `SUPABASE_URL` set hai toh Supabase, warna SQLite.
- Default file: `instance/docuquery.db`

### Kya changes kar sakte hain?
- **Mode force** kar sakte ho env var se (testing ke liye)
- SQLite me bhi **vector search** hai (brute-force cosine) — chhote data par
  theek, bade par slow (tab Supabase hi sahi)
- Local file ko export/migrate kar sakte ho Supabase me

### Fayada?
- **"Always works"** guarantee — internet na ho, key na ho, phir bhi chalega
- Extractive preview ke saath combo = fully offline demo

---

## 7. Security Layer — Werkzeug Hashing + Signed Tokens

### Kyu use kiya?
- **Werkzeug scrypt** — Flask ke saath built-in aata hai, battle-tested
  password hashing (PBKDF2/scrypt family).
- **itsdangerous (URLSafeTimedSerializer)** — Flask ka official token library
  — signed + timestamped tokens bina kisi extra dependency ke.

### Kahan hai?
- Hashing: `routes.py register() / change_password()` — `generate_password_hash`
  / `check_password_hash`
- Tokens: `routes.py issue_token() / verify_token()` — 8-hour max age, salt
  `"docuquery-auth-token"`
- `_current_user()` — 3 token sources + cookie fallback

### Kya changes kar sakte hain?
- **bcrypt/argon2** — scrypt se bhi strong modern hash (library add hogi)
- **Refresh tokens** — short-lived access token + long refresh token (abhi
  single 8-hour token hai — simple, demo ke liye enough)
- **Rate limiting** on login (brute-force protection) — Flask-Limiter se
- **2FA** future me (package #2-4 ke saath ja sakta hai)

### Fayada?
- Zero extra dependencies (Werkzeug + itsdangerous Flask ke saath hi aate hain)
- Token stateless hai — DB me session table nahi chahiye
- Security basics strong hain (hashing, expiry, enumeration protection, RLS)

---

## 8. pypdf (PDF Parsing)

### Kyu use kiya?
- Pure Python — koi system dependency nahi (har machine par chalta hai).
- Page-wise text extraction milta hai — page citations ke liye zaroori.

### Kahan hai?
- `docuquery/pdf_processing.py` — `parse_pdf_bytes()`, `_split_sections()`
  (heading detection), `_chunk_text()` (1250/180), `_guess_title()`

### Kya changes kar sakte hain?
- **PyMuPDF (fitz)** — faster + better layout (tables/columns), thoda heavy
- **OCR add** (pytesseract) — scanned PDFs ke liye (future roadmap me hai)
- **Table extraction** (pdfplumber) — scientific papers ke tables ke liye
- Chunking strategies: semantic chunking (LLM se) — better quality, zyada cost

### Fayada?
- Zero-dependency, reliable
- Section detection → chunks ko context milta hai (RAG me useful)

---

# 🎯 Ek Page Ka Summary (ratt lo!)

| Technology | KYU | KYA BADAL SAKTE HO | FAYADA |
|---|---|---|---|
| **Flask** | Lightweight, app factory | FastAPI, blueprints split, rate limiting | Simple, testable |
| **Supabase + pgvector** | Free, vector DB built-in, RLS | Embedding dim, hybrid search, index type | Ek hi DB, free, secure |
| **RAG pattern** | Grounded + verifiable answers | top_k, reranking, memory | Hallucination control |
| **Groq (gpt-oss-20b)** | Free, fast, JSON output | Model swap, temperature, provider swap | ₹0, 2-4s answers |
| **Hashing/MiniLM embed** | Demo-safe, upgrade path | Enable MiniLM, bigger models | Har machine par chalta hai |
| **SQLite fallback** | Offline demo mode | Force mode, migrate to Supabase | "Always works" |
| **Werkzeug + signed tokens** | Built-in, battle-tested | bcrypt, refresh tokens, 2FA | Zero deps, stateless |
| **pypdf** | Pure Python, page-wise | PyMuPDF, OCR, table extraction | Reliable, portable |

---

## 🗣️ 30-second "Kyun" Pitch (jab sir poochein)

> *"Har choice ek constraint ke hisaab se ki — **free me, har laptop par, aur
> honestly chalna chahiye**. Flask lightweight hai isliye; Supabase me pgvector
> built-in hai isliye alag vector DB ki zarurat nahi; Groq free aur fast hai
> isliye; embeddings me hashing default hai taaki demo kabhi na tootte; aur
> SQLite fallback hai taaki internet ke bina bhi project chale. RAG pattern
> isliye ki answers grounded hon aur page citations se verify ho sakein."*

**Aur ek line extra (impression ke liye):**
> *"Jahan quality chahiye wahan upgrade path rakhi hai — MiniLM embeddings,
> model swap, hybrid search — sab config-level changes hain, code rewrite
> nahi."*
