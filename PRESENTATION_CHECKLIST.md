# DocuQuery — Presentation Preparation Notes

Demo flow, likely questions and talking points.

---

## 1. Before the demo

- [ ] Run the app once end-to-end the day before (10 min)
- [ ] Verify login (`demo@example.com` / `demo123`) and one AI answer
- [ ] Laptop charged; mobile hotspot available as internet backup
- [ ] `python run.py` command ready in a terminal
- [ ] Project report (.docx) and presentation (.pptx) available in `docs/`
- [ ] No other project tabs open — just the app and these notes

---

## 2. Demo flow (10 minutes)

### Opening (30 s)
> "Good morning sir. My project is **DocuQuery** — a research-paper reading
> assistant that finds information in PDFs and answers questions with page
> citations, so every claim can be verified against the source."

### Problem (30 s)
> "Research papers are long — methods, data and limitations are buried deep.
> Generic summaries do not show where an answer came from. This project solves
> exactly that."

### Live demo (5–6 min)
1. Login with the demo account.
2. Open the 144-page paper from the library.
3. **Research Brief** → point at the `[p. N]` citations.
4. **Evidence Trail** → "these are the exact source excerpts behind each claim".
5. **Ask This Paper** → `What is pre-training and what data is used for it?`
6. **Download** button (`.md` / `.txt` / `.json`).
7. **Profile** → files, password change, clear history (show only).

### Architecture (1 min)
> "The pipeline is Retrieval-Augmented Generation: passages are embedded as
> 384-d vectors, searched with cosine similarity (pgvector HNSW index), and the
> LLM answers only from the retrieved context — which is why the citations are
> accurate. Stack: Flask + Supabase PostgreSQL + Groq, all free tier."

### Closing (20 s)
> "The test suite has 38+ automated tests, a 144-page paper is indexed in about
> 10 seconds, and the app also runs without any API key in extractive preview
> mode. Thank you sir — happy to take questions."

---

## 3. Likely questions

| Question | Suggested answer |
|---|---|
| What is RAG? | Retrieval-Augmented Generation — retrieve the relevant passages first, then have the LLM answer from that context only. Answers stay grounded in the document. |
| What is the tech stack? | HTML, CSS, Bootstrap and vanilla JavaScript on the frontend; Python (Flask) at the backend; Supabase (PostgreSQL + pgvector) for the database; Groq as the LLM API. |
| How does it reduce hallucination? | The model receives only the paper's passages and is instructed to answer strictly from them, with page citations the reader can check. |
| How is it different from a general chatbot? | A general chatbot answers from general knowledge. This tool answers only from the uploaded paper and shows the exact page references. |
| What are embeddings? | Fixed-length numeric vectors (384 dimensions here) that represent meaning, so similar passages can be found by cosine similarity. Default backend is feature hashing; MiniLM is supported as an option. |
| Why Supabase? | Managed PostgreSQL with pgvector — vector search happens inside the database (HNSW index), with row-level security. Free tier is enough for this scale. |
| What if there is no internet? | The app runs offline too: SQLite storage and an extractive preview that quotes the paper's own sentences (clearly labelled). |
| How is security handled? | Hashed passwords (Werkzeug), signed session tokens, per-account data isolation, RLS on every table, and only a server-side service role accesses the database. |
| What are the limitations? | No OCR for scanned PDFs yet; complex tables/figures/equations are not extracted; the scope is single-paper analysis. All listed under future enhancements. |
| What did you build yourself? | The full stack — system design, Flask backend, RAG pipeline, frontend, database schema and the test suite. The report's implementation chapter documents each module. |
| How would it scale? | pgvector HNSW scales with data size; Groq's paid tiers raise rate limits; file storage is already on Supabase Storage. |
| Future scope? | OCR, multi-paper comparison, BibTeX export, email-based password reset, retrieval-quality evaluation, cloud deployment. |
| Is it deployed? | It is deployment-ready: a Render.com blueprint (render.yaml) and a Dockerfile are included. The code is hosted on GitHub. |

---

## 4. Numbers worth remembering

| Item | Value |
|---|---|
| Tests | 38+ passing |
| Big paper demo | 144 pages → 887 passages → ~10 s |
| Answer time | 2–4 s |
| Upload limit | 50 MB |
| Cost | ₹0 (free tiers) |

---

## 5. Common mistakes to avoid

1. Trying untested changes during the demo — show only the tested flow.
2. Speaking too fast — keep a steady pace and point at the screen.
3. Arguing over an interruption — "That is a good question, the approach is…"
4. If something fails: "One minute sir, I will restart the server." → `python run.py` → continue calmly.
5. Always end the verification story with: *important claims should be verified
   against the original paper* — that is the core design goal of the tool.
