# DocuQuery — Project Synopsis

**Offline, on-device research assistant for scientific PDFs**
Flask · SQLite · llama.cpp + Qwen2.5 · no cloud services

## Abstract

DocuQuery lets a student or researcher upload a scientific paper, receive a structured
research brief, and ask questions that are answered with page-level citations. The whole
system runs on a single laptop: PDF text extraction, chunking, embeddings, vector search,
summaries, question answering and the web interface. The language model is a quantised
Qwen2.5 GGUF file executed locally by llama.cpp. Documents, embeddings and accounts never
leave the machine, and the application makes no request to any third-party service after
the one-time setup download.

## Problem statement

Reading research papers is slow. Generic chatbots summarise papers quickly but:

- they upload the document to a cloud provider, which is a problem for unpublished or
  personal work;
- they invent details because they answer from general knowledge, not the paper;
- they rarely tell the reader which page supports which claim;
- they need API keys, accounts and a stable internet connection.

DocuQuery is built around the opposite constraint: the document must stay on the device,
every claim must point back to a page, and the tool must keep working when the network is
gone.

## Objectives

1. Extract text page by page from a text-based PDF and index it locally.
2. Produce a structured brief (objective, methodology, dataset, findings, limitations,
   conclusion) with inline page citations.
3. Answer free-form questions through retrieval-augmented generation over the same
   passages, again with page citations.
4. Run entirely offline after setup, on ordinary laptop hardware, without GPU requirements.
5. Store everything locally (SQLite + plain files) with per-account separation of papers.
6. Degrade gracefully: if no model is available, show the closest retrieved passages
   instead of failing.

## System architecture

```
Browser (127.0.0.1:5000)
   │
   ├── Flask app  ── routes/API, sessions, validation
   │     ├── pdf_processing.py   PDF text + page + section extraction
   │     ├── embeddings.py       hashing vectoriser (offline, no model)
   │     ├── repository.py       SQLite: users, papers, chunks, summaries, chat
   │     ├── storage.py          original PDFs on disk (instance/uploads/…)
   │     ├── rag.py              retrieval, prompting, extractive fallback
   │     └── llm.py              Ollama or any OpenAI-compatible local server
   │
   └── llama.cpp server (127.0.0.1:8080)  Qwen2.5 GGUF, started by local_ai.py
```

`local_ai.py` prepares the runtime and model on first use, picks a model that suits the
laptop's RAM, starts the model server, launches the web app, and hot-swaps the model when
a different one is chosen on the Profile page.

## Modules

| Module | Responsibility |
| --- | --- |
| `docuquery/__init__.py` | application factory, blueprints, security headers, CORS policy |
| `docuquery/config.py` | environment-driven configuration with safe local defaults |
| `docuquery/routes.py` | pages, auth API, upload, summary, ask, model picker, health |
| `docuquery/pdf_processing.py` | page-aware text extraction, section detection, chunking |
| `docuquery/embeddings.py` | deterministic hashing embeddings (optional sentence-transformers) |
| `docuquery/repository.py` | SQLite schema, account scoping, vector search, history |
| `docuquery/storage.py` | local PDF storage with path-traversal protection |
| `docuquery/rag.py` | retrieval, context formatting, extractive fallback |
| `docuquery/llm.py` | local model adapters, JSON summary parsing, length presets |
| `docuquery/model_registry.py` | model discovery, RAM-based recommendation, saved choice |
| `local_ai.py` | runtime/model download, server lifecycle, supervision, hot swap |

## Technology stack (and why)

| Choice | Reason |
| --- | --- |
| Flask | small, readable, easy to run locally; no server infrastructure needed |
| SQLite | file database, zero configuration, keeps per-user data on the laptop |
| PyPDF | pure-Python text extraction with page boundaries |
| Hashing embeddings | no second model download; deterministic and fast for a single document set |
| llama.cpp + Qwen2.5 GGUF (0.5B/1.5B/3B) | runs on CPU, quantised to keep the download ~0.4–2 GB |
| Vanilla JS + local CSS | no CDN, so the interface works offline |

Removed in the offline version: Groq API, Supabase (database/storage/auth) and Google
Sign-In. See [OFFLINE_PRIVACY.md](OFFLINE_PRIVACY.md).

## Data flow

1. **Upload** — the PDF is validated, stored under `instance/uploads/<paper-id>/`, parsed
   page by page, split into passages and embedded.
2. **Summary** — the most relevant passages for six research questions are retrieved and
   sent to the local model with a strict JSON schema; the reply is validated and stored
   with the page markers used as evidence.
3. **Question** — the question is embedded, the closest passages are retrieved, and the
   model answers with citations. Length is chosen in the chat box (Short/Balanced/Detailed).
4. **Evidence** — the UI shows the page chips, and clicking one opens the original PDF at
   that page.

## Privacy properties

- No cloud database, bucket, model API or OAuth provider.
- Only `127.0.0.1` sockets; proxy settings are ignored for model calls.
- No analytics, telemetry, external fonts or CDN assets.
- The single outbound connection in the project's lifetime is the first-run download
  (PyPI packages, llama.cpp binaries, GGUF model).

Details and verification steps: [OFFLINE_PRIVACY.md](OFFLINE_PRIVACY.md).

## Performance notes

| Model | Typical CPU speed | Use |
| --- | --- | --- |
| Qwen2.5 0.5B | 20–40 tokens/s | quick lookups, low-RAM laptops |
| Qwen2.5 1.5B | 8–15 tokens/s | default for 8 GB laptops |
| Qwen2.5 3B | 4–8 tokens/s | 16 GB laptops, better prose |

A `--gpu` flag switches to a Vulkan build of llama.cpp for 2–5× faster answers on
integrated or discrete GPUs. Shortening the retrieved context (`RAG_TOP_K`,
`SUMMARY_CONTEXT_CHARS`) also cuts answer time.

## Limitations

- Text-based PDFs only; scanned documents need OCR first.
- Small models can misread numbers or cite the wrong page; citations must be checked.
- Accounts are local and intentionally simple (no email verification, no 2FA).
- Files are unencrypted on disk; rely on OS disk encryption for a shared laptop.
- Designed for one user on one machine, bound to loopback.

## Future work

- Optional OCR pipeline for scanned PDFs.
- Cross-paper search and comparison within one account.
- Encrypted local database and optional app-level passphrase.
- Export a brief to Markdown/PDF for submission.
- Streaming answers so long responses appear progressively.

## References

- Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, 2020.
- Qwen Team, *Qwen2.5 Technical Report*, 2024.
- llama.cpp project documentation (ggml-org/llama.cpp).
- Flask and SQLite documentation.
