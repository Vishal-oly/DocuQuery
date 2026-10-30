# DocuQuery — Backend Process, Step-by-Step (Yaad Karne Wali Script)

Ye document **rattne ke liye** hai. Har process ki steps numbered hain, aur har
process ke end me ek **"BOLNA YE HAI"** block hai — viva/presentation me wahi
lines bolni hain. 3 baar padh lo — automatic yaad ho jayega.

---

## 🧠 Sabse pehle: 6-words ki kundli (ye ratta lagao, baaki sab isi par latkti hai)

```
PARSE  →  CHUNK  →  EMBED  →  STORE  →  RETRIEVE  →  GENERATE
(PDF se    (tukde   (numbers  (DB me    (dhoondho    (LLM se
 text)     banao)   banao)    rakho)    relevant)    jawab)
```

**Har upload inhi 6 steps se guzarta hai. Har question last 3 steps se.**
Ye 6 word bolte hi lag jao — examiner ko lagega flow tumhe aata hai.

---

# PROCESS 0 — Server Start (`python run.py`)

1. `run.py` → `create_app()` call hota hai (Flask **app factory** pattern).
2. `config.py` `.env` file load karta hai — do tarike se: `python-dotenv`
   (agar installed ho) + **manual fallback parser** (BOM-safe) — taaki
   environment kabhi missing na rahe.
3. Config decide karti hai:
   - `SUPABASE_URL` + service key set hai → **Supabase pgvector mode**
     (warna **SQLite** local mode — offline demo)
   - `GROQ_API_KEY` set hai → **AI mode** (warna extractive preview)
4. Blueprint (`/api/*`) register hota hai, CORS headers lagte hain (embedded
   iframes ke liye).
5. Server bind hota hai `0.0.0.0:5000` par.
6. `GET /api/health` hamesha batata hai kaunsa mode chal raha hai.

> **BOLNA YE HAI:** *"Server app factory se start hota hai. Config pehle .env
> load karti hai — do layer me, taaki kisi machine par bhi keys miss na hon.
> Phir decide hota hai ki database Supabase hoga ya local SQLite, aur AI on hai
> ya nahi. Health endpoint ye sab honestly report karta hai."*

---

# PROCESS 1 — Register (naya account)

1. Browser se aata hai: `POST /api/register` with `{name, email, password}`.
2. `_validate_credentials()` check karta hai: email sahi format? password ≥ 6
   characters? Name khaali toh nahi?
3. Password **hash** hota hai (Werkzeug scrypt) — plain text **kabhi** store
   nahi hota.
4. `save_user()` → `users` table me row (id, name, email, password_hash).
5. `issue_token(user_id)` — ek **signed token** banata hai (SECRET_KEY se
   signature, **8 ghante** ki validity).
6. Response: `201` + `{user, token}`. Frontend token localStorage me save
   karta hai.

**Duplicate email** → `400 Email already registered`.

> **BOLNA YE HAI:** *"Register par password ko turant hash kar diya jaata hai —
> plain text kabhi nahi hota. Uske baad ek signed token milta hai jo 8 ghante
> valid hai. Token me data chhupa nahi hota — sirf user id hota hai, signature
> secret key se hoti hai, isliye koi forge nahi kar sakta."*

---

# PROCESS 2 — Login

1. `POST /api/login` with `{email, password}`.
2. Email se user dhoondha jaata hai (`get_user_by_email`).
3. `check_password_hash()` — password match?
4. **Galat email YA galat password dono par same message**: "Invalid email or
   password" — taaki koi bata na sake ki kaunsa email exist karta hai
   (enumeration protection).
5. Match → `issue_token()` → `200` + token.

**Google login:** `POST /api/auth/google` → Google ki ID token verify hoti hai
(server-side, audience check) → same email = same account, naya email = auto
register.

> **BOLNA YE HAI:** *"Login par password hash verify hota hai. Ek security
> detail yaad rakho — galat email aur galat password par bilkul same error
> aata hai, taaki koi ye pata na laga sake ki kaunsi emails registered hain."*

---

# PROCESS 3 — Har API call par Auth (token verification)

Ye har protected endpoint par hota hai — isliye **decorators** hain:
`@api_login_required` (API → 401 JSON) aur `@page_login_required` (page →
redirect `/login`).

1. `_current_user()` token teeno jagah se dhoondhta hai:
   - `Authorization: Bearer <token>` header (normal case)
   - `?token=<token>` (downloads, embedded iframes — cookies block hote hain wahan)
   - `X-Auth-Token` header (extra fallback)
   - aur phir Flask **cookie session** (fallback)
2. `verify_token()` — signature check + 8-ghante max age. Invalid/expired →
   `None`.
3. Valid → user DB se load → `session_id` = user ki id (data isolation ka
   master key).
4. Koi token valid nahi → `401 Please sign in to continue.`

**Data isolation:** har paper, har chunk, har query ek `session_id` ke under
rehti hai — kisi aur ka data kisi ko nahi milta. Supabase par **RLS** (row-level
security) bhi lagi hai — double protection.

> **BOLNA YE HAI:** *"Har request par token teen tarike se accept hota hai —
> header, URL parameter, ya cookie. Ye isliye kyunki embedded iframes me
> browsers cookies block kar dete hain. Token verify hone ke baad user ka
> session_id ban jaata hai jo har query me filter lagata hai — data isolation
> isi se hai."*

---

# PROCESS 4 — UPLOAD (⭐ Sabse important — poora yaad karo)

**Mnemonic: Parse → Chunk → Embed → Store → Retrieve → Generate**

1. **File check** — `pdf` field hai? Naam `.pdf` par khatam hota hai?
   → `400 "Only PDF files are supported."`
2. **Size check** — `MAX_UPLOAD_MB = 50`. Bada file → `413` (Flask khud
   reject karta hai).
3. **PARSE** — `parse_pdf_bytes()`:
   - pypdf se page-wise text nikalta hai
   - password-protected PDF → error: "This PDF is password-protected..."
   - scanned PDF (text layer nahi) → upload chalta hai, brief me **OCR notice**
   - `_sanitize_text()` control characters hatata hai
4. **CHUNK** — do cheezein:
   - `_split_sections()` — headings detect karta hai (Abstract, Methods,
     Results...) taaki har chunk ko section tag mile
   - `_chunk_text()` — **1,250 characters** ke chunks, **180 ka overlap**
     (overlap isliye ki jawab chunk ki boundary par cut na ho)
   - Example: 1 page → 7 chunks | 144 pages → **887 chunks, ~10 seconds**
5. **EMBED** — `embeddings.py` har chunk ko **384-dimension vector** deta hai:
   - Default: `HashingEmbedder` (feature hashing — zero dependencies, demo-safe)
   - Optional: MiniLM sentence-transformers (semantic, `requirements-embeddings.txt`)
6. **STORE** — do jagah:
   - PDF file → `storage.py` (Supabase Storage bucket "papers" / local
     `uploads/`). **Storage fail ho toh flow nahi rukta** — warning log, demo
     safe rehta hai.
   - Data → `repository.save_paper()` + `save_chunks()` — chunks me jaata hai:
     `id, paper_id, session_id, page_number, section, content, embedding`
     (pgvector me HNSW index, cosine similarity)
7. **GENERATE (brief)** — `rag.make_summary()`:
   - pehle top-2 relevant passages **retrieve** hote hain (RETRIEVE step yahan
     bhi lagta hai — isliye mode ka naam "Groq **RAG**" hai)
   - Groq key hai → `generate_structured_summary()` — LLM strict **JSON** deta
     hai: objective, dataset, methodology, key_findings, limitations,
     conclusion, overall_summary — sab **`[p. N]` page citations** ke saath
   - key nahi hai → `extractive_summary()` — paper ki **apni best sentences**
     quote hoti hain, clearly labelled "extractive preview"
8. **Final response** `201`:
   `{ paper, summary, chunk_count, database, text_char_count }`

**Error contract (ratt lo):**

| Case | Status | Message |
|---|---|---|
| Non-PDF | 400 | "Only PDF files are supported." |
| Corrupt | 400 | "This file does not look like a valid PDF." |
| Password-protected | 400 | "This PDF is password-protected..." |
| Too big | 413 | (Flask) |
| DB/embedding down | 503 | service error |

> **BOLNA YE HAI:** *"Upload me 6 steps hote hain — Parse, Chunk, Embed,
> Store, Retrieve, Generate. PDF pehle clean text banti hai, phir section
> detection ke saath 1,250 characters ke chunks bante hain 180 overlap ke
> saath. Har chunk ka 384-dimension embedding banta hai aur pgvector me save
> hota hai. Brief ke liye hum pehle relevant passages retrieve karke LLM ko
> dete hain — isi liye RAG — aur model page citations ke saath structured JSON
> deta hai. 144-page paper me 887 chunks lagbhag 10 seconds me ban jaate hain."*

---

# PROCESS 5 — ASK (Question-Answering)

1. `POST /api/papers/<id>/ask` with `{question}`.
2. Question validate: khaali nahi? ≤ 1,200 characters?
3. **Ownership check** — paper is `session_id` ka hai? (nahi → `404 Paper not
   found in this account.`)
4. **RETRIEVE** — question ka embedding banta hai → **cosine similarity** se
   top-k passages dhoondhe jaate hain (pgvector HNSW index).
5. Koi relevant passage nahi mila → honest jawab: *"no matching passages found
   in this paper"* — guess nahi karte.
6. **Open-book context** — `format_context()`: passages ko page/section labels
   ke saath arrange karta hai (cap: 18,000 characters).
7. **GENERATE** — `answer_from_context()`:
   - System prompt ki shart: **"Sirf is context se jawab do. Agar jawab context
     me nahi hai toh bolo ki paper me iska jawab nahi hai. Har claim ke aage
     page number `[p. N]` lagao."**
   - Ye **anti-hallucination ka main mechanism** hai!
8. `citation_sources()` — Evidence Trail: har source ka page number, section,
   excerpt.
9. Response: `{ answer, sources, mode }` — mode: `"Groq RAG"` / `"no-match"`.

**LLM fail ho jaaye toh** — specific error message + retrieved passages khud
dikh dete hain ("Here are the closest retrieved passages instead..."). Kabhi
bhi silent failure nahi.

> **BOLNA YE HAI:** *"Question aate hi hum uska embedding banate hain aur
> pgvector me cosine similarity se top passages dhoondhte hain. Ye passages ek
> open-book context ban kar Groq ko jaate hain. System prompt ki shart hai ki
> model sirf isi context se jawab de, page citations lagaye, aur agar jawab
> paper me hi nahi hai toh saaf bol de — guess na kare. Isi liye hallucination
> control hota hai. Har claim ko user Evidence Trail me page number ke saath
> verify kar sakta hai."*

---

# PROCESS 6 — Download & View Original PDF

1. **Brief download** — `GET /api/papers/<id>/download?format=md|txt|json`:
   - `_summary_as_markdown()` brief ko format karta hai (sources ke saath)
   - unknown format → `400`
   - URL me `?token=` isliye kyunki ye browser ka **native download** hai —
     wahan custom header nahi lagta.
2. **View PDF** — `GET /api/papers/<id>/file` → `storage.read()` file stream
   karta hai. Ek smart detail: local DB + cloud file ka mix dikhe toh
   **auto-repair** kar leta hai.

---

# PROCESS 7 — Delete & Clear History

1. `DELETE /api/papers/<id>` — paper + uske chunks (DB me `on delete cascade`)
   + stored PDF file — teeno delete.
2. `POST /api/me/clear-history` — user ke **saare** papers, chunks, chats
   (`clear_session_data`). Response: `{"deleted": N}`.
   - UI me **two-click confirm** hai (galti se sab na udd jaaye) — ye frontend
     ki baat hai, backend sirf ek call hai.

---

# PROCESS 8 — Modes ki kahani (2x2 table — ye exam me bahut puchta hai)

| | **Groq key hai** | **Groq key nahi** |
|---|---|---|
| **Supabase set hai** | Full AI mode — "Groq RAG", cloud DB, cloud storage | Extractive preview — paper ki apni sentences, labelled |
| **Supabase nahi** | AI + local SQLite | Pura offline demo — SQLite + extractive |

Har mode UI me **clearly labelled** hota hai — koi chhupata nahi. Health
endpoint par sab kuch dikhta hai. Yehi **honest design** ka selling point hai.

> **BOLNA YE HAI:** *"Project 4 modes me chalta hai — Supabase aur Groq dono
> hone par full AI mode. Key na hone par hum extractive preview dete hain jo
> clearly labelled hota hai — hum kabhi pretend nahi karte ki AI hai. Offline
> demo ke liye SQLite fallback bhi hai, isliye internet ke bina bhi project
> chal jaata hai."*

---

# PROCESS 9 — Security ki 6 baatein (ratt lo, 30 second me bolni hain)

1. **Passwords** — Werkzeug scrypt hash, plain text kabhi nahi.
2. **Tokens** — signed (SECRET_KEY), 8-hour expiry, uid only.
3. **Error messages** — login par same message (enumeration protection).
4. **Data isolation** — session_id filter har query par + **Supabase RLS**.
5. **Service key** — sirf server `.env` me, browser/kabhi client ko nahi.
   `.gitignore` me excluded.
6. **Upload limits** — 50 MB cap, PDF-only, filename `secure_filename()` se
   sanitize.

---

# 🎤 Final Rehearsal — 60-second poora backend pitch

> *"Backend Flask me hai — app factory pattern, blueprint-based routes. Data
> Supabase PostgreSQL me hai pgvector ke saath, offline fallback SQLite hai.
> Upload ka pipeline 6 steps ka hai: Parse, Chunk, Embed, Store, Retrieve,
> Generate. PDF se clean text banti hai, section-wise chunks bante hain, unka
> 384-dimension embedding pgvector me jaata hai. Question aane par cosine
> similarity se top passages milti hain, wo Groq ko context ke roop me jaati
> hain, aur model page citations ke saath grounded jawab deta hai — ya phir
> honestly bol deta hai ki paper me jawab nahi hai. Passwords hashed hain,
> tokens signed hain, aur har user ka data session isolation plus RLS se alag
> rehta hai."*

---

# ⚡ Rapid Fire (1-line answers)

| Sawal | Jawaab |
|---|---|
| Framework? | Flask — app factory + blueprints |
| Database? | Supabase PostgreSQL + pgvector (fallback: SQLite) |
| Vector search? | Cosine similarity, HNSW index, 384-d embeddings |
| Chunking? | 1,250 chars, 180 overlap, section-aware |
| LLM? | Groq API, model `openai/gpt-oss-20b`, free tier |
| Hallucination control? | Context-only prompting + page citations + honest refusal |
| Password storage? | Werkzeug scrypt hash |
| Token lifetime? | 8 hours, signed with SECRET_KEY |
| Upload limit? | 50 MB, PDF only |
| Tests? | 42 pytest cases — auth, repository, RAG, PDF, API |
| Offline mode? | SQLite + extractive preview (clearly labelled) |
| Biggest design choice? | Honesty — har fallback labelled, koi fake AI nahi |

---

## 📌 Rattne ka plan (3 din)

**Din 1:** Sirf upar wali **6-words kundli** + Process 4 (upload) — ye 80% hai.
**Din 2:** Process 5 (ask) + Process 8 (modes table).
**din 3:** Baaki processes skim + 60-second pitch 3 baar bol ke dekho + rapid fire.

*Jab tak 60-second pitch bina ruke bol sako — backend tumhe aata hai.* 💪
