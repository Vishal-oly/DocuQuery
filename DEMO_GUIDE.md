# DocuQuery — Demo Guide

Setup instructions and a short demo walkthrough.

---

## Quick Start

```bash
# 1. Open the project folder
cd DocuQuery

# 2. Create an environment and install dependencies (first time only)
python -m venv .venv
# Windows:   .venv\Scripts\activate
# Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 3. Run
python run.py
```

Open **http://127.0.0.1:5000** in the browser.

The `.env` file is already configured (Supabase database + Groq LLM).
Demo account:

| Field | Value |
|---|---|
| Email | `demo@example.com` |
| Password | `demo123` |
| Library | 2 sample papers pre-loaded (144-page LLM Survey + a short sample) |

---

## Demo Walkthrough (5 minutes)

1. **Login** with the demo account.
2. **Workspace** → open *A Survey of Large Language Models* from the library.
3. **Research Brief** → objective, dataset, methodology, findings and
   limitations, each with page citations like `[p. 26]`.
4. **Evidence Trail** → the exact source excerpts behind every claim, so any
   reader can verify against the original PDF.
5. **Ask This Paper** → try:
   - `What is pre-training and what data is used for it?`
   - The answer is generated only from the paper's passages and carries
     page + section references.
6. **Summaries page** → download the brief as `.md`, `.txt` or `.json`.
7. **Profile** → uploaded files, password change, clear history
   (two-step confirmation).

Note: the 144-page paper is indexed as 887 passages in about 10 seconds.

---

## How it works (short version)

1. *Retrieval-Augmented Generation* — every answer is grounded in passages
   retrieved from the uploaded paper, with page citations for verification.
2. Passages are embedded as 384-dimensional vectors and searched with
   cosine similarity (pgvector HNSW index).
3. Stack: Flask + Supabase PostgreSQL/pgvector + Groq LLM, with a local
   SQLite + extractive preview fallback that needs no external services.

---

## Key numbers

| Item | Value |
|---|---|
| Automated tests | 38+ (pytest) |
| 144-page paper indexing | 887 passages in ~10 s |
| Answer latency | ~2–4 s (Groq free tier) |
| Upload limit | 50 MB |
| Cost | Free tier only |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Port 5000 busy | `set PORT=5001` (Windows) / `PORT=5001 python run.py` (Mac) |
| `ModuleNotFoundError` | run `pip install -r requirements.txt` again |
| "Server is not responding" | restart with `python run.py` |
| No internet | rename `.env` to `.env-offline` — the app falls back to SQLite + extractive preview mode |
| Supabase error | check `SUPABASE_URL` in `.env` |

---

## Note on secrets

The `.env` file contains API keys. Keep the folder private; this file is
already excluded from git (see `.gitignore`).

---

## Package contents

```
DocuQuery/
├── docuquery/        ← Application (Flask backend + frontend)
├── tests/            ← Automated test suite
├── docs/             ← Project report (.docx), presentation (.pptx), diagrams
├── examples/         ← Sample research papers
├── schema/           ← Supabase SQL setup
├── instance/         ← Local demo database (offline mode)
├── .env              ← Pre-configured (Supabase + Groq keys)
├── README.md         ← Full documentation
└── run.py            ← Start command
```
