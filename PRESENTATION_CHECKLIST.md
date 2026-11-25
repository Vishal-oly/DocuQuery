# Presentation Checklist — DocuQuery (offline / on-device)

## Before the presentation

- [ ] `start.bat` runs without errors and prints **"Model ready"**
- [ ] Model already downloaded (`models\*.gguf` exists) — no waiting on the day
- [ ] Test account created; sample PDF uploaded; one summary already generated
- [ ] Two questions rehearsed (one answerable, one out of scope)
- [ ] Internet-off test done once at home
- [ ] Laptop charged, charger packed, sleep disabled during the demo
- [ ] Backup: screenshots of the summary and an answer, in case the model is slow
- [ ] Browser zoom at ~110%, dark/light theme consistent
- [ ] Terminal window size such that "Model ready" and "DocuQuery starting" are visible

## Slide outline (8–10 slides)

1. **Title** — DocuQuery: offline research assistant for scientific PDFs.
2. **Problem** — papers take long to read; cloud chatbots upload documents, hallucinate and
   give no page-level evidence.
3. **Goal** — same convenience, but on-device, citation-grounded, offline-capable.
4. **Architecture** — one diagram: browser → Flask → SQLite → retrieval → llama.cpp server.
5. **Pipeline** — upload → page extraction → chunking → embeddings → retrieval → brief.
6. **What the user sees** — screenshot of the structured brief with `[p. 4]` citations.
7. **Q&A with evidence** — screenshot of a question, answer and evidence chips; mention
   Short/Balanced/Detailed length switch.
8. **Privacy & offline** — the four privacy cards: on-device AI, local storage, loopback
   sockets, no analytics/CDN. State that Groq, Supabase and Google Sign-In were removed.
9. **Model choice** — 0.5B/1.5B/3B table, RAM-based recommendation, `--gpu`, hot swap from
   the Profile page.
10. **Results, limits, future work** — speed numbers, small-model caveats, OCR and
    cross-paper search as next steps.

## Key numbers to quote

| Point | Number |
| --- | --- |
| Model download (one time) | 0.4 GB (0.5B) / 1.0 GB (1.5B) / 2.0 GB (3B) |
| Runtime download | ~25 MB (CPU) or ~40 MB (Vulkan) |
| Answer speed, 1.5B on CPU | ~8–15 tokens/s (20–60 s per summary) |
| Default answer length | 120–250 words (switchable to 300–450) |
| Upload limit | 20 MB |
| Tests | 65 passing, no network or model needed |

## Likely questions and short answers

**"Is the data really not uploaded?"**
Yes — after setup, disconnect the internet and it still works. Show
`Get-NetTCPConnection` with `127.0.0.1`, and DevTools showing only localhost requests.

**"Which cloud did you remove?"**
Groq (text generation), Supabase (database, storage, auth) and Google Sign-In. The
`requirements.txt` no longer lists `groq` or `supabase`, and there is no `google_auth.py`.

**"Why not use an API? It would be better quality."**
Quality vs privacy and cost. The architecture keeps a model adapter, so a cloud backend
can be added later without touching the retrieval code — but the default must work
offline for confidential papers.

**"What if the model gives a wrong answer?"**
Retrieval restricts it to the paper's passages, every claim carries a page marker, and if
the model is unavailable the app shows the retrieved excerpts instead of inventing text.
Small models are treated as a drafting aid, not an authority.

**"How is it different from a ChatGPT PDF plugin?"**
Runs locally, no account/API key, no per-page upload, works offline, citations in the UI,
open source and inspectable.

**"How would you scale it to a department?"**
SQLite → PostgreSQL, loopback → authenticated LAN deployment, per-user quotas, and a
larger model on a shared GPU box. The current build deliberately stays single-user.

## Do not

- Do not demo on a fresh extract: the first-run download would eat the presentation time.
- Do not claim the model is always correct; say citations let the reader verify.
- Do not run with `HOST=0.0.0.0` on public Wi-Fi.
- Do not delete `instance/` before the demo — that removes the uploaded PDF and summaries.
