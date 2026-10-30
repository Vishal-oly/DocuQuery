# DocuQuery — Frontend Guide (Sourabh & Saeem ke liye)

Ye document frontend ka poora code samjhaata hai — file by file, flow by flow.
Itna detail me hai ki bina code khole bhi picture clear ho jayegi. Beech me
`code snippets` diye hain — unhe actual files me mila lena.

**Project root:** `DocuQuery/`
**Frontend ka ghar:** `docuquery/templates/` (HTML) + `docuquery/static/` (JS + CSS)

---

## 1. Big Picture — frontend karta kya hai?

```
Browser (HTML/CSS/JS)  ──REST API (JSON)──►  Flask backend (/api/...)
        │                                        │
        │  localStorage me token                 ├─ Supabase (database)
        │  fetch() calls                         └─ Groq (AI)
        ▼
   User ko dikhata hai: Upload, Research Brief, Chat, Library, Profile
```

Important baatein:
- **Koi framework nahi hai** (React/Vue nahi) — plain HTML + CSS + vanilla JavaScript (ES6). Bootstrap 5 CSS use hota hai styling ke liye.
- Frontend ka kaam sirf **UI + API calls** hai — saara business logic backend me hai.
- Har page ka apna chhota JS file hai (neeche table me hai).
- API se baat karne ka ek hi tarika hai: `DQ.apiFetch()` (dq.js me) — token automatically attach ho jaata hai.

---

## 2. File Map — kaunsi file kya karti hai

### HTML templates (`docuquery/templates/`)

| File | Page | Kya hai isme |
|---|---|---|
| `landing.html` | `/` | Bina login wala homepage — project intro, features, login/register links |
| `login.html` | `/login` | Login + Register (ek hi page, tabs se switch) + optional Google button |
| `forgot.html` | `/forgot` | Password reset — email → code → new password |
| `index.html` | `/workspace` | **Main app** — upload, research brief, chat, library (ye dil hai) |
| `summaries.html` | `/summaries` | Saare generated briefs ki list + download buttons |
| `profile.html` | `/profile` | Name/password change, uploaded files, clear history, logout |

### JavaScript (`docuquery/static/`)

| File | Size | Zimmedaari |
|---|---|---|
| `dq.js` | 120 lines | **Common helper** — token storage, `apiFetch`, form binding. Har page par chalta hai |
| `app.js` | 414 lines | **Workspace** — upload, brief render, chat, library |
| `auth.js` | 335 lines | Login/Register/Forgot pages ka form handling |
| `summaries.js` | 220 lines | Summaries list + downloads |
| `profile.js` | 285 lines | Profile page — forms, files, clear history |

### CSS

| File | Kya style karta hai |
|---|---|
| `styles.css` | Workspace/summaries/profile ka layout (dark sidebar, chat bubbles, cards) |
| `auth.css` | Login/register/forgot pages (split-screen design) |

---

## 3. `dq.js` — sabse pehle ye samjho (dil hai iska)

Ye chhoti file har page par load hoti hai. Iska kaam: **login token sambhalna aur
API calls banana**.

### 3.1 Token kahan rehta hai?

```js
function getToken() {
  return window.localStorage.getItem(TOKEN_KEY) || '';   // save: localStorage
}
```

Token login ke baad milta hai (server se JSON me) aur `localStorage` me save
hota hai. `clearToken()` logout par hata deta hai.

**Teen extra jagah se bhi token aa sakta hai** (security nahi, convenience ke liye):
1. `Authorization: Bearer <token>` header (normal case)
2. URL me `?token=...` — `captureUrlToken()` ise kheench kar localStorage me daal deta hai, phir URL se hata deta hai (taaki link share karne par token na dikhe)
3. `X-Auth-Token` header

> **Interview tip:** "Token URL me kyun?" — answer: kuch embedded/iframes me
> cookies block ho jaate hain; tab `?token=` fallback kaam aata hai. Ye
> `captureUrlToken()` handle karta hai.

### 3.2 `apiFetch(url, options)` — API call ka standard rasta

```js
async function apiFetch(url, options = {}) {
  // 1. token attach: ?token=... (header bhi jaata hai)
  // 2. fetch() with 90-second timeout
  // 3. 401 aaye → token clear + /login par bhej do
  // 4. response JSON parse → error ho toh throw
}
```

Koi bhi naya API call likhna ho toh **hamesha** `DQ.apiFetch()` use karo,
direct `fetch()` mat karo — warna token attach nahi hoga.

### 3.3 `bindForm(form, button, inputs)` — Enter key fix

Ye form ko bind karta hai taaki **button click + Enter key** dono kaam karein —
even in embedded iframes jahan browser native form submit block kar deta hai.

---

## 4. `app.js` — Workspace page (main app)

Page structure (index.html): **left sidebar** (section links + library) | **middle**
(upload + research brief) | **right** (chat). Neeche status bar.

### 4.1 Upload journey — "User ne PDF select kiya..."

```
user file select karta hai (browse ya drag-drop)
        │
        ▼
uploadFile(file)                          ← app.js:244
  ├─ check: sirf .pdf?        nahi → setAlert('Please select a PDF file.')
  ├─ check: size ≤ 50 MB?     nahi → setAlert('...larger than 50 MB...')
  ├─ FormData banao: formData.append('pdf', file)
  ├─ setUploading(true)       → progress bar + button disable
  ├─ await api('/api/upload', { method: 'POST', body: formData })
  │        │
  │        ▼  server ka JSON: { paper, summary, chunk_count, database, ... }
  │
  ├─ chatMessages.replaceChildren()     → purana chat saaf
  ├─ setPaper(payload.paper, chunk_count) → sidebar + brief section update
  ├─ setAlert('Ready: <title> · N passages indexed · <mode>.', 'success')
  └─ finally: setUploading(false) + input reset
```

`setUploading(true/false)` progress bar chalata hai (`.upload-progress` bar) aur
browse button disable/enable karta hai.

### 4.2 Research Brief render — `renderSummary(summary)`

Server se `summary` object aata hai:

```js
{
  objective, dataset, methodology, key_findings, limitations,
  conclusion, overall_summary,
  mode: "Groq RAG" | "extractive preview",
  sources: [ { page_number, section, content }, ... ]
}
```

`renderSummary()` har field ko uski card me daalta hai. `mode` ke hisaab se
upar wala banner dikhta hai (AI mode ya "extractive preview" notice).

`renderSources(sources, ...)` — Evidence Trail list: har source me page number
badge (`[p. 26]`), section name, aur excerpt ka text.

### 4.3 Chat journey — "User ne question pucha..."

```
user: "What is pre-training?"  (input + Enter ya Send button)
        │
        ▼
sendQuestion(question)                     ← app.js:287
  ├─ addMessage('user', question)          → chat me user bubble
  ├─ showTyping()                          → 3-dot typing indicator
  ├─ await api(`/api/papers/<id>/ask`, { method:'POST', body:{question} })
  │        │
  │        ▼  server: { answer, sources, mode }
  │
  ├─ $('#typingIndicator')?.remove()
  ├─ if (epoch !== chatEpoch) return;      → IMPORTANT (neeche samjhaaya)
  └─ addMessage('assistant', answer, sources, mode)   → AI bubble + citations
```

**`chatEpoch` kya hai?** Agar user ne answer aane se pehle chat clear kar diya,
toh purana answer phir bhi render na ho jaaye — isliye har clear par epoch
badhta hai aur `sendQuestion` check karta hai. (Race condition ka simple fix.)

**Suggestion chips:** chat input ke neeche pre-made questions ke buttons hain —
click par `sendQuestion(chipText)` call hota hai.

### 4.4 Library (sidebar)

```js
renderLibrary(papers)   // papers ki list banaata hai (title + date)
loadLibrary()           // GET /api/papers → renderLibrary()
selectPaper(id)         // GET /api/papers/<id> → setPaper() + chat reset
deleteActivePaper()     // DELETE /api/papers/<id> → confirm dialog → list refresh
```

`setPaper(paper, chunkCount)` — active paper set karta hai: title, brief,
evidence, chat context sab update hota hai. `setPaperSectionsEnabled(false)`
jab koi paper selected nahi — tab brief/ask sections disabled dikhte hain.

### 4.5 Chhoti magar kaam ki cheezein

| Function | Kaam |
|---|---|
| `setAlert(msg, kind)` | Upar ka banner (error red / success green) |
| `showToast(msg)` | Neeche corner ka chhota notification (3.6s) |
| `setActiveSection(name)` | Sidebar me current section highlight |
| `api(url, options)` | Wrapper around `DQ.apiFetch` — bas convenience |

---

## 5. `auth.js` — Login / Register / Forgot

**Login page ka design:** left side marketing panel, right side form card.

| Function | Kaam |
|---|---|
| `setMode('login' \| 'register')` | Tabs switch — form fields/labels badalte hain |
| `validate()` | Submit se pehle checks: email format, password ≥ 6 chars, register par name + confirm-password match |
| `setFieldError(input, errorId, msg)` | Field ke neeche red error text |
| `busy(button, true/false)` | Submit ke waqt button disable + "Please wait..." |
| `bindSwitchLinks()` | "Create account" / "Sign in" wale links jo mode switch karte hain |

**Login submit flow:**
```
form submit → validate() → busy(true)
  → POST /api/login  { email, password }
  → success: DQ.setToken(token) + localStorage me user → window.location = '/workspace'
  → error: setAlert(server ka message)  (jaise "Invalid email or password")
```

**Register:** same, but `POST /api/register { name, email, password }` — 201 par
token milta hai aur seedha workspace.

**Forgot password (`forgot.html` + auth.js ka second block):**
3 steps ek hi form card me: email → reset code → new password. Har step par
alag `POST /api/forgot` / `POST /api/reset`.

**Google button:** agar server ne `google_client_id` bheja hai tabhi button
dikhta hai (`login.html` me server-side check). Google se ID token aata hai →
`POST /api/auth/google` → token milta hai.

---

## 6. `summaries.js` — Summaries page

- `loadPapers()` → `GET /api/papers` → `renderList()` — cards: title, date, size, mode badge
- Card click → `selectPaper(id)` → `renderSummary()` + `renderSources()` (detail view)
- **Download buttons** — 3 formats:

```js
function turl(url) {
  return DQ.withToken(url);   // URL me ?token=... attach karta hai
}
// GET /api/papers/<id>/download?format=md | txt | json
```

Download isliye `?token=` ke saath jaata hai kyunki ye **browser ka native
download** hai (anchor click) — wahan custom header nahi laga sakte.

---

## 7. `profile.js` — Profile page

| Section | UI | API |
|---|---|---|
| Personal details | name input + Save | `PATCH /api/me` |
| Security | current + new password | `POST /api/me/password` |
| Uploaded files | list (title, size, date) + View/Remove | `GET /api/papers`, file/DELETE APIs |
| Clear history | **two-click confirm** (pehle "Clear", phir "Yes, clear everything") | `POST /api/me/clear-history` |
| Logout | button | `POST /api/logout` + `DQ.clearToken()` → `/login` |

`clear-history` ka two-click pattern deliberately hai — galti se sab data na
ud jaaye. Pehle click par button ka text badal jaata hai ("Confirm?"), doosra
click API call karta hai.

---

## 8. CSS ka chhota sa map (jab design badalni ho toh)

| Kya badalna hai | Kahan jao |
|---|---|
| Colors/theme (green accent, dark sidebar) | `styles.css` top variables + `.sidebar`, `.topbar` |
| Chat bubbles | `styles.css` — `.chat-message.user`, `.chat-message.assistant` |
| Upload dropzone (dashed border) | `.dropzone`, `.dropzone.dragover` |
| Login page split design | `auth.css` — `.auth-aside`, `.auth-card` |
| Buttons | `.btn`, `.btn-primary`, `.btn-danger` |
| Toast | `.toast` |

---

## 9. End-to-end story (interview ke liye — yaad rakhlo)

> "User login karta hai → `dq.js` token localStorage me save karta hai →
> workspace par PDF drag karta hai → `app.js uploadFile()` pehle client-side
> validate karta hai (PDF? size?) phir FormData se `/api/upload` ko POST karta
> hai → server brief + paper JSON deta hai → `renderSummary()` + `renderSources()`
> usse UI me dikhate hain → user chat me question puchta hai → `sendQuestion()`
> `/api/papers/<id>/ask` ko call karta hai → answer + page citations chat bubble
> me render hote hain."

## 10. Common questions (frontend)

| Q | A |
|---|---|
| Token kahan store hota hai? | `localStorage` (dq.js), plus cookie fallback server-side |
| Upload se pehle validation kyun? | User ko turant feedback + bandwidth bachti hai; real check server par bhi hoti hai |
| `chatEpoch` kyun? | Clear-chat vs late-answer race condition rokne ke liye |
| Framework kyun nahi? | Simple SPA-like workspace plain JS se manage ho jaata hai — kam dependencies, fast load |
| 401 par kya hota hai? | `dq.js apiFetch` token clear karke `/login` par redirect kar deta hai |
| Download me token kaise jaata hai? | `turl()`/`withToken()` URL me `?token=` attach karte hain |

---

*Ye guide project ke current code par based hai (tests: 42 passing). Koi doubt
ho toh pehle `dq.js` (120 lines) padh lo — 5 minute me aadha frontend clear ho
jayega.*
