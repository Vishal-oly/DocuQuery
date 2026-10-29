# DocuQuery — Scientific Paper Research Assistant

DocuQuery is a student minor-project web app for reading scientific-paper PDFs. Upload or reopen a paper, get a structured research brief, inspect page-linked evidence, and ask follow-up questions grounded in retrieved passages.

**Stack:** HTML, CSS, JavaScript, Bootstrap 5, Python, Flask, Supabase PostgreSQL/pgvector, Groq. A local SQLite mode and extractive preview keep the project runnable before external services are configured.

## What the app does

- **Workspace:** one responsive research dashboard for a selected paper.
- **Guest Home & Auth:** a public home page plus email/password login and registration; papers and briefs are saved to the account.
- **Upload PDF:** browse or drag and drop a text-based PDF (20 MB default limit).
- **Research Brief:** overview, objective, methodology, data/materials, findings, limitations, and conclusion.
- **Evidence Trail:** retrieved excerpts retain page numbers and section labels so readers can verify claims in the original paper.
- **Ask This Paper:** ask a focused question or use a suggested prompt; responses cite supporting pages.
- **Paper Library:** reopen or remove papers stored for the current browser session.
- **Storage and models:** Supabase/pgvector and Groq are configurable; SQLite, deterministic feature-hashing vectors, and an extractive/retrieval preview are available for local demonstration.

## Workflow

```text
Research PDF
  → Flask upload and validation
  → PyPDF page-wise text extraction
  → scientific-section detection and overlapping chunks
  → 384-dimensional vectors (hashing by default; optional MiniLM)
  → Supabase pgvector or local SQLite
  → retrieve relevant, page-linked passages
  → Groq research brief / grounded answer
  → display result with an evidence trail
```

The app is a single-page workspace. The navigation links jump to Workspace, Upload PDF, Research Brief, Evidence Trail, Ask This Paper, and Paper Library.

## Run locally

Python 3.10 or later is recommended.

### 1. Create an environment and install dependencies

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux:       source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. Add optional service credentials

```bash
cp .env.example .env
```

- Leave Supabase fields blank for local SQLite mode.
- Add a Groq API key to `GROQ_API_KEY` to enable generated briefs and answers. Without it, the app labels its extractive/retrieval preview clearly.
- Set `FLASK_SECRET_KEY` to a long random value before deploying. For example: `python -c "import secrets; print(secrets.token_hex(32))"`.
- `.env` is ignored by Git. **Never commit API keys or the Supabase service-role key.**

The sample Groq model ID is configurable using `GROQ_MODEL`; replace it with a model enabled for your Groq account if needed.

### 3. Start DocuQuery

```bash
python run.py
```

Open `http://127.0.0.1:5000`. The server binds to `0.0.0.0` for container and preview hosting.

Use `examples/sample_scientific_article.pdf` to test the upload flow. It is a synthetic sample created for this project; its study, authors, and results are fictional. Regenerate it with:

```bash
python examples/generate_demo_pdf.py
```

## Configure Supabase (optional)

1. Create a Supabase project.
2. In the Supabase SQL Editor, run [`schema/supabase.sql`](schema/supabase.sql).
3. Set these values in `.env`:

```dotenv
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVER_ONLY_SERVICE_ROLE_KEY
```

4. Restart Flask. The header status will indicate that Supabase is connected.

The service-role key is used only by the Flask server. It must never be added to browser JavaScript. The SQL enables row-level security and limits direct table access to the server-side service role.

## Deploy (free)

### Render.com — recommended (full features, 50 MB uploads)

1. Push this repo to your GitHub account
2. On [render.com](https://render.com) → **New → Blueprint** → connect the repo
   (it reads `render.yaml` automatically)
3. Fill the prompted secrets when asked:
   - `SUPABASE_URL` — `https://<ref>.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY` — Supabase → Settings → API → service_role
   - `GROQ_API_KEY` — console.groq.com → API Keys
   - `GOOGLE_CLIENT_ID` — optional
4. Deploy → your app gets a `https://docuquery.onrender.com` URL

Uploads up to **50 MB** work (`MAX_UPLOAD_MB`), and PDFs are kept in
**Supabase Storage** (`SUPABASE_STORAGE_PRIMARY=true`) so they survive restarts.

### Fly.io / Docker

A `Dockerfile` is included — `fly launch` or any Docker host works with the
same environment variables.

### Vercel — demo only (limited)

Vercel serverless caps request bodies at **4.5 MB** and has an ephemeral
filesystem, so big PDFs and "View Document" will not work. If you only need a
small-PDF demo, wrap `run:app` with `@vercel/python` and set the same env vars.

## Optional: Google Sign-In

The login page can show a **Continue with Google** button (one-tap sign-in). Google
users are signed in instantly; first-time Google emails get an account automatically.

1. Open [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**
2. **Create Credentials** → **OAuth client ID** → Application type **Web application**
3. Under **Authorized JavaScript origins** add your app URL(s), e.g.:
   - `http://127.0.0.1:5000`
   - `http://localhost:5000`
   - your deployed/preview URL
4. Copy the **Client ID** and set it in `.env`:

```dotenv
GOOGLE_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
```

5. Restart Flask. The button appears on `/login`. (No client secret needed — the app
   verifies Google ID tokens server-side.)

> Note: when the app is embedded in a third-party iframe, popup-based sign-in may
> be blocked — open the app in a normal browser tab to use Google sign-in.

## Optional: MiniLM embeddings

The default `hashing` embedder is deterministic, offline, and lightweight. It is a baseline—not a transformer semantic model. To use the optional local Sentence Transformers model:

```bash
python -m pip install -r requirements-embeddings.txt
```

Then set in `.env`:

```dotenv
EMBEDDING_BACKEND=sentence-transformers
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

The model downloads on first use. Both backends produce 384-dimensional vectors.

## Test

```bash
python -m pip install -r requirements-dev.txt
pytest -q
```

Tests cover the Flask home/health API, PDF upload, session scoping, local vector search, PDF section/chunk processing, and deterministic embeddings. Groq and Supabase credentials are not needed for the local test suite.

## Project structure

```text
DocuQuery/
├── docuquery/                 # Flask application package
│   ├── templates/index.html   # Single-page workspace
│   ├── static/                # CSS and browser JavaScript
│   ├── routes.py              # UI and JSON API endpoints
│   ├── pdf_processing.py      # PDF extraction and chunking
│   ├── embeddings.py          # Hashing / optional MiniLM
│   ├── repository.py          # Supabase and SQLite persistence
│   ├── rag.py                 # Retrieval, brief, citations, Q&A
│   └── llm.py                 # Groq client adapter
├── docs/                      # Navigation diagram and project notes
├── examples/                  # Synthetic sample PDF
├── schema/supabase.sql        # Supabase tables and vector-search RPC
├── tests/                     # pytest test suite
├── .env.example               # Safe configuration template
└── run.py                     # Local entry point
```

## API overview

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/` | Guest Home page (about, features, Login/Register) |
| `GET` | `/login` | Login / Register page |
| `GET` | `/workspace` | Research workspace (requires sign-in) |
| `POST` | `/api/register` | Create an account and sign in |
| `POST` | `/api/login` | Sign in with email/password |
| `POST` | `/api/logout` | Sign out |
| `GET` | `/api/me` | Current signed-in user |
| `GET` | `/api/health` | Database, model, and upload-limit status |
| `GET` | `/api/papers` | List papers in the signed-in account |
| `GET` | `/api/papers/<id>` | Reopen a paper and its saved brief |
| `POST` | `/api/upload` | Validate, process, store, and summarize a PDF |
| `POST` | `/api/papers/<id>/ask` | Retrieve evidence and answer a question |
| `DELETE` | `/api/papers/<id>` | Remove a paper and its chunks |

## Scope, privacy, and limitations

- The prototype supports selectable text in PDFs; scanned/image-only PDFs require OCR, which is not included.
- Extraction of complex tables, figures, equations, and multi-column layouts may be incomplete.
- Accounts use email/password authentication with hashed passwords; papers are scoped to the signed-in account. Add rate limiting and stronger session controls before public deployment.
- Generated summaries and answers can be wrong or incomplete. Verify important claims against the PDF and the displayed page-linked excerpts.
- Local SQLite is intended for development/demo use. Configure Supabase for managed storage; use a hardened WSGI deployment and a strong secret key for production.

## Project documents

- [Minor project synopsis](docs/PROJECT_SYNOPSIS.md)
- [Navigation diagram (SVG)](docs/NAVIGATION_DIAGRAM.svg)
- [Navigation diagram (PNG)](docs/NAVIGATION_DIAGRAM.png)
- [Repository-pattern analysis](docs/REPO_ANALYSIS.md)
