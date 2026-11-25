> **Updated architecture note (offline edition):** DocuQuery now runs entirely on one laptop —
> Flask + SQLite + a local Qwen GGUF model served by llama.cpp. Groq, Supabase and Google
> Sign-In were removed, the UI no longer loads CDN assets, and only `127.0.0.1` sockets are used.
> Cloud-specific sections below are kept as project history. For how it works today see
> [the offline & privacy guide](OFFLINE_PRIVACY.md) and [project synopsis](PROJECT_SYNOPSIS.md).

# Public repository analysis and design decisions

This note summarizes public examples reviewed for the project concept. The implementation in this workspace is written independently; repository code is used as an architectural reference, not copied.

## 1. RAGDoc Assistant — Yatendra-Gupta193

Repository: <https://github.com/Yatendra-Gupta193/RAGDoc_Assistant>

The README describes HTML/CSS/JavaScript, Flask, Supabase/pgvector, PDF upload, chunking, semantic retrieval, and page references. The inspected Flask file keeps upload parsing, embedding calls, Supabase writes, retrieval, and LLM provider setup together in one application module. It retains the PDF page number on each extracted chunk and scopes retrieval to a browser-session ID.

**What we reuse conceptually:** page-aware PDF extraction, per-paper chunking, pgvector similarity search, and source references.

**What this version changes:** separates extraction, embeddings, storage, RAG, and HTTP routes into modules; loads secrets from environment variables; supports local SQLite before Supabase is available; includes a research-paper-specific structured summary; and uses an extractive fallback when Groq is not configured.

## 2. Scientific Paper RAG — lalalalafeier

Repository: <https://github.com/lalalalafeier/scientific-paper-rag>

Its project documentation emphasizes section detection, chunk-quality checks, evidence retrieval, citation traces, and evaluation notes for scientific PDFs. It is a paper-level pipeline rather than the same Flask/Supabase web app.

**What we reuse conceptually:** scientific-paper section labels and the idea that summaries should be inspectable against retrieved evidence.

**What this version changes:** adds a Bootstrap-oriented browser workspace, persistent paper history, question answering, and a Supabase pgvector schema.

## 3. RAG paper summarization example — torchstack-ai

Repository: <https://github.com/torchstack-ai/rag-summarization-pdf>

This is a Python RAG pipeline that downloads an academic paper, processes the PDF, builds a Chroma vector store, and creates a summary. It helped validate the core ingestion → retrieval → generation flow, but is not the target Flask/Supabase user interface.

## 4. Design summary for DocuQuery

- **Ingestion:** PDF text extraction retains page numbers; section names are detected with conservative heading rules.
- **Retrieval:** relevant passages are selected before generation; source cards remain visible in the UI.
- **Generation:** a local Qwen2.5 GGUF model runs through llama.cpp on the laptop. Embeddings stay a separate backend (hashing by default) so generation and retrieval use different mechanisms.
- **Persistence (current):** local SQLite only; PDFs live in `instance/uploads/`. Supabase/pgvector was removed in the offline edition.
- **Safety/limitations:** no cloud keys exist to leak; LLM prompts are restricted to the retrieved text and the app falls back to those passages when no model runs; scanned PDFs need OCR and the local accounts are single-device by design (see `OFFLINE_PRIVACY.md`).
