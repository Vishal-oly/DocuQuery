# DocuQuery — Complete Walkthrough

Every screen, button and function of the system, with live-tested behaviour.

---

## 0. Starting the app

```bash
python run.py
# Flask server starts at http://127.0.0.1:5000
```

`run.py` → `create_app()` → loads config (`.env`) → selects Supabase/SQLite →
registers routes.

**Health check:** `GET /api/health`
```json
{"database": "Supabase pgvector", "embedding_backend": "hashing",
 "llm_available": true, "llm_model": "openai/gpt-oss-20b",
 "max_upload_mb": 50, "status": "ok"}
```
These six values show which mode the app is running in.

---

## 1. Guest pages (before login)

| Page | URL | Content | Backend function |
|---|---|---|---|
| Landing page | `/` | Project intro, feature list, login/register links | `home_page()` |
| Login / Register | `/login` | Form with tabs (Sign in / Create account) | `login_page()` |
| Forgot password | `/forgot` | Email → reset code → new password | `forgot_page()` |

---

## 2. Authentication

### Register — `POST /api/register`
Input `{name, email, password}` → validated by `_validate_credentials()` →
password hashed with Werkzeug scrypt (never stored in plain text) →
`save_user()` → response `201` with `{user, token}`.

### Login — `POST /api/login`
`get_user_by_email()` → `check_password_hash()` → `issue_token()` (signed
token, 8-hour lifetime). The token is accepted from three sources —
`Authorization: Bearer` header, `?token=` query parameter, or a cookie — so the
app also works when embedded in iframes where cookies are blocked.

### Error cases

| Case | Response |
|---|---|
| Wrong password | `400/401 Invalid email or password` |
| Duplicate email | `400 Email already registered` |
| Invalid/expired token | `401 Please sign in to continue.` |
| Missing token | `401` → UI redirects to `/login` |

### Google Sign-In — `POST /api/auth/google`
Verifies the Google ID token server-side (`google_auth.py →
verify_google_credential`). Existing emails join their account; new emails get
an account automatically. Enabled by setting `GOOGLE_CLIENT_ID` in `.env`.

### Password reset
`POST /api/forgot` issues a time-limited reset code; `POST /api/reset` sets the
new password.

---

## 3. Upload pipeline (the core)

**UI:** Browse / drag-and-drop → `uploadFile()` (app.js) → `POST /api/upload`

Internal steps:
```
1. Validate   → PDF only, size ≤ MAX_UPLOAD_MB (50 MB)
2. Extract    → pdf_processing.parse_pdf_bytes() — page-wise text,
                _sanitize_text() removes control characters
3. Chunk      → _split_sections() (Abstract/Methods/... detection) +
                _chunk_text() (1,250 chars, 180 overlap)
4. Embed      → embeddings.py — 384-d vectors (feature hashing / MiniLM)
5. Store      → repository.save_paper() + save_chunks() (Supabase pgvector)
   + Brief    → rag.make_summary() → Groq structured summary
                (or extractive preview when no key is configured)
```

Observed results: 1-page sample → 7 chunks; 144-page survey → 887 chunks in
~10 seconds.

### Error cases

| Case | Response |
|---|---|
| Non-PDF file | `400 "Only PDF files are supported."` |
| Corrupt file with .pdf name | `400 "This file does not look like a valid PDF."` |
| Larger than 50 MB | `413` (upload limit) |
| Password-protected PDF | `400 "This PDF is password-protected..."` |
| Scanned PDF (no text layer) | Upload succeeds; brief shows an OCR notice |

---

## 4. Research Brief

Generated together with the upload. Fields:

| Field | Meaning |
|---|---|
| `objective` | Research goal of the paper |
| `dataset` | Data / materials used |
| `methodology` | How the study was done |
| `key_findings` | Main results |
| `limitations` | Stated or implied limitations |
| `conclusion` | Closing claims |
| `overall_summary` | Short overall summary |
| `sources` | Evidence trail: page + section + excerpt |
| `mode` | `Groq RAG` (AI) or `extractive preview` (offline fallback) |

---

## 5. Ask This Paper (Q&A)

**UI:** chat box → `sendQuestion()` (app.js) → `POST /api/papers/<id>/ask`

Pipeline: question → embedding → top-k passage retrieval (pgvector cosine
similarity) → Groq answers strictly from that context → answer + citations.

Two honest fallbacks (by design):
- Retrieval finds nothing relevant → `"no matching passages"` mode.
- The passages do not contain the answer → the model says so instead of
  guessing. This is the main anti-hallucination behaviour.

Chat helpers: Clear button (resets the conversation), suggestion chips.

---

## 6. Paper Library

| Control | Function | API |
|---|---|---|
| Paper click | `selectPaper()` — loads brief, evidence, chat | `GET /api/papers/<id>` |
| Delete | `deleteActivePaper()` — removes paper, chunks and PDF | `DELETE /api/papers/<id>` |
| View Document | Opens the original PDF | `GET /api/papers/<id>/file` |
| Download | Brief as `.md` / `.txt` / `.json` | `GET /api/papers/<id>/download?format=` |

---

## 7. Summaries page (`/summaries`)

Lists every generated brief with download buttons. Backed by
`GET /api/papers`, `download_summary()` and `_summary_as_markdown()`.

---

## 8. Profile page (`/profile`)

| Section | Control | API |
|---|---|---|
| Personal details | Save changes (name) | `PATCH /api/me` |
| Security | Update password | `POST /api/me/password` |
| Uploaded files | View / Remove | file + DELETE APIs |
| Clear history | Two-click confirm — wipes papers, briefs, chats | `POST /api/me/clear-history` |
| Logout | Clears the session | `POST /api/logout` |

---

## 9. Backend function map

| File | Main functions | Role |
|---|---|---|
| `routes.py` | `register, login, google_login, logout, me, update_me, change_password, forgot_password, reset_password, health, list_papers, get_paper, upload_pdf, ask_paper, delete_paper, get_paper_file, download_summary, summarize, clear_history` | REST API |
| `routes.py` helpers | `issue_token, verify_token, _current_user, _sign_in, api_login_required, page_login_required, _validate_credentials` | Auth & tokens |
| `pdf_processing.py` | `parse_pdf_bytes, _split_sections, _chunk_text, _guess_title, _sanitize_text` | PDF → clean chunks |
| `embeddings.py` | `make_embedder` | Text → 384-d vectors |
| `rag.py` | `retrieve_summary_chunks, format_context, citation_sources, extractive_summary, make_summary, answer_question` | RAG core |
| `llm.py` | `_call_groq, generate_structured_summary, answer_from_context` | Groq API calls |
| `repository.py` | `save_user, get_user_by_email, save_paper, save_chunks, list_papers, get_paper, delete_paper, set_reset_token, get_user_by_reset_token, update_user_name, update_user_password` | Database layer |
| `storage.py` | `FileStorage: save, read, exists, delete, delete_paper` | PDF storage (local + Supabase Storage) |
| `google_auth.py` | `verify_google_credential` | Google ID-token verification |

## 10. Frontend function map

| File | Functions | Role |
|---|---|---|
| `app.js` | `uploadFile, setUploading, sendQuestion, addMessage, renderSummary, renderSources, selectPaper, deleteActivePaper, renderLibrary, loadLibrary, setPaper, showToast, setAlert` | Workspace |
| `auth.js` | login/register form handling, mode switch, forgot/reset flow, `onGoogleCredential` | Auth pages |
| `dq.js` | `DQAuth: getToken, setToken, clearToken, withToken, apiFetch (90 s timeout), bindForm, captureUrlToken, rewriteLinks` | Shared auth helper |
| `summaries.js` | brief list + download handlers | Summaries page |
| `profile.js` | name/password forms, file list, clear-history (two-click), logout | Profile page |

---

## 11. Operating modes

| Situation | Behaviour |
|---|---|
| Supabase + Groq configured | Full AI mode (`Groq RAG`), cloud DB, cloud file storage |
| No Groq key | `extractive preview` — quotes the paper's own sentences (clearly labelled) |
| No Supabase | Local SQLite mode |
| No internet (rename `.env`) | Offline demo: extractive + SQLite |
| Scanned/image PDF | Upload works; brief shows an OCR notice |
| Server down | Browser shows "Server is not responding (timed out)" → restart `python run.py` |

---

## 12. Verified behaviour summary

| Step | Result |
|---|---|
| Pages (/, /login, /forgot) | 200 |
| Register | 201 + token |
| Wrong password / duplicate / bad token | 400 / 400 / 401 |
| Invalid uploads | 400 with clear messages |
| Upload real paper | 201, chunks indexed, brief generated |
| Q&A | Grounded answers + honest refusals + sources |
| Downloads md/txt/json | 200 (unknown format: 400) |
| View original PDF | 200 |
| Profile (me, rename, password) | 200 |
| Password reset flow | 200 |
| Library (list/select/delete) | 200 |
| Clear history | 200 |
| Health | Supabase pgvector + Groq + 50 MB |

---

## 13. Suggested demo order

1. Health endpoint (shows the active mode).
2. Login → 144-page paper → Research Brief (point at citations).
3. Ask This Paper — one good question and one the paper cannot answer
   (demonstrates grounded refusal).
4. Download the brief (`.md`).
5. View Document (original PDF).
6. Profile → clear history (show only).
7. Optional: run `python -m pytest -q` in the terminal — the suite passes.
