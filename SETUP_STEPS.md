# DocuQuery Offline — Complete Setup Guide (Hinglish)

Ab kuch bhi alag se install karne ki zaroorat nahi: **model bhi app khud download kar legi**. Bas Python chahiye aur `start.bat` double-click.

**Download (Google Drive):** https://drive.google.com/file/d/1FuCBrrGnaK9cUAUgAhSSykFQ8-9zrIL8/view

---

## Step 0 — Kya chahiye

| Cheez | Zaroori? |
|---|---|
| Python 3.10+ | Haan (ek baar install) |
| Ollama / LM Studio | **Nahi** — app khud model setup kar leti hai |
| Internet | Sirf pehli baar (~1.1 GB download) |
| Google account / API key / Supabase | Nahi, kuch bhi nahi |

Laptop: 8 GB RAM wala normal laptop kaafi hai. GPU optional.

---

## Step 1 — ZIP extract karo

Downloaded `DocuQuery-Offline-v3.zip` par **right-click → Extract All** → folder `DocuQuery-Offline`.

Yaad rakho: folder ko `C:\Program Files` mein na rakho (wahan write permission nahi hoti). Desktop / Documents / `C:\Users\Vishal\...` theek hai.

---

## Step 2 — Python install karo (ek hi baar)

1. https://www.python.org/downloads/ → **Python 3.12** download.
2. Installer ki pehli screen par **"Add python.exe to PATH"** tick karo → **Install Now**.
3. Check: PowerShell kholo aur
   ```powershell
   python --version
   ```
   `Python 3.12.x` dikhe → done. "not recognized" aaye → installer dobara chala kar PATH add karo.

---

## Step 3 — App chalao (`start.bat`)

Folder ke andar **`start.bat`** double-click karo. Ye khud hi:

1. `.venv` (virtual environment) banayega,
2. Flask aur baaki dependencies install karega,
3. pehli baar **AI runtime (~25 MB) + model (~1 GB)** download karega,
4. model server start karke app chalu karega.

Pehli baar total **5–15 minute** (internet speed par depend). Download progress terminal mein dikhega:

```
Downloading the llama.cpp runtime (b12651, about 25 MB) ...
   runtime ready (24 files)
Downloading Qwen2.5 1.5B Instruct (about 1 GB, one time only) ...
   model: 10% (105 MB of 1046 MB)
   ...
Model server ready on http://127.0.0.1:8080/v1
DocuQuery starting at http://127.0.0.1:5000
```

**Uske baad kabhi dobara download nahi hoga** — file `models/` folder mein save rehti hai.

### Windows ke bajaye macOS / Linux

```bash
cd ~/Downloads/DocuQuery-Offline
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python local_ai.py
```

---

## Step 4 — App kholo

Browser mein: **http://127.0.0.1:5000**

1. **Create account** → naam, email, password (sirf aapke laptop par save hota hai).
2. Login karo.
3. `examples/sample_scientific_article.pdf` upload karo (test ke liye).
4. **Generate summary** dabao — pehla summary 20–60 sec le sakta hai.
5. **Ask a question** — jawab page references ke saath milega.

**Footer check:** **"Local model ready · qwen2.5-1.5b-instruct"** dikhe → AI chalu hai.
**"Preview mode"** dikhe → model server nahi chal raha (neeche troubleshooting).

---

## Step 5 — Roz use karna (offline)

1. `start.bat` double-click (ya `python local_ai.py`)
2. Browser: **http://127.0.0.1:5000**

Bas. Internet ki zaroorat nahi, Ollama/LM Studio ki zaroorat nahi.

> Terminal window band karne par app aur model server dono band ho jayenge. Use karte waqt window minimize karke rakho.

---

## Model kaun sa use hoga — aur badalna kaise

**Pehli baar me automatic choice:** app aapke laptop ki RAM dekh kar model chunti hai (kam RAM → 0.5B, theek-thaak → 1.5B, zyada → 3B). Aapko kuch set nahi karna.

**Laptop mein pehle se jo model hai use karna:**

```powershell
cd "C:\path\to\DocuQuery-Offline"
.venv\Scripts\python.exe local_ai.py --list-models
```

Ye aapke computer ke saare GGUF models dikhayega — is app ke `models` folder ke, **LM Studio** ke models, aur custom folders ke. Jo pasand aaye uska `id`/path use karo:

```powershell
.venv\Scripts\python.exe local_ai.py --model-path "C:\Users\Vishal\.lmstudio\models\qwen\model.gguf"
```

**App ke andar se switch karna:**

1. Login karke **Profile** page kholo.
2. Neeche **AI model** card mein sare available models dikhenge (size, source, "recommended" tag).
3. Ek select karo → **Use selected model** dabao.
4. `start.bat`/`local_ai.py` se chala rahe ho to model **turant switch** ho jayega (kuch second ruk kar jawab dena). Warna next start par apply hoga.

**Doosre folder ko scan karana ho** to `.env` mein:
```ini
EXTRA_MODEL_DIRS=D:\models;E:\gguf
```

## Answer chhota kyun aata hai — aur bada kaise karein

Default answer **balanced** hai (~120–250 words). Chat box ke andar **Clear** ke paas ek dropdown hai:

| Option | Length | Kab |
|---|---|---|
| **Short** | ~80 words tak | sirf quick fact / page number |
| **Balanced** | ~120–250 words | normal sawaal (default) |
| **Detailed** | ~300–450 words | poora explanation, numbers, caveats |

Har sawaal ke saath badal sakte ho — choice yaad bhi rehti hai. Default badalna ho to `.env`:
```ini
ANSWER_DETAIL=detailed
ANSWER_MAX_TOKENS=1200
SUMMARY_MAX_TOKENS=1200
```

⚠️ Lambe jawab zyada time lenge (CPU par), aur chhote model (0.5B) lambe text mein bhatak jaate hain — page numbers verify kar lena.

## Model se answer mein kya fark padta hai

| Model | Speed (laptop CPU) | Answer ki quality |
|---|---|---|
| 0.5B | sabse tez | chhote seedhe jawab, kabhi page number galat |
| 1.5B | medium | theek structure, usually sahi citations — **default** |
| 3B | dheema | sabse behtar wording aur reasoning, 16 GB RAM par |

**Coder models** (`Qwen2.5-Coder`) programming ke liye tune hote hain — paper ke prose answers unse kamzor aate hain. Plain **Instruct** model choose karo.

## Speed badhane ke tareeke

**1. Chhota model (sabse bada fayda)**
```powershell
cd "C:\path\to\DocuQuery-Offline"
.venv\Scripts\python.exe local_ai.py --model small
```
0.5B model ~400 MB ka hai aur 1.5B se **2–4x tez** jawab deta hai. Quality thodi kam hoti hai, par summary/answers theek aate hain.

**2. GPU use karo (agar laptop mein GPU hai — Intel/AMD/NVIDIA sab)**
```powershell
.venv\Scripts\python.exe local_ai.py --gpu
```
Pehli baar Vulkan build download hoga. Switch karne se pehle `runtime` folder delete kar do, warna purana CPU build hi use hoga. Integrated GPU par bhi 2–5x speed mil sakti hai.

**3. Settings se tuning** — `.env` mein:
```ini
RAG_TOP_K=3
SUMMARY_CONTEXT_CHARS=6000
LOCAL_AI_CONTEXT=4096
```
Kam text model ko bhejoge to jawab jaldi aayega.

**4. Pehla jawab hamesha slow hota hai** — model RAM mein load hota hai. Uske baad ke jawab tez hote hain.

> Speed ka sabse bada factor: **model ka size** aur **GPU**. 0.5B + `--gpu` sach mein fast feel hota hai.

## Optional settings (`.env`)

`.env.example` ki copy banao aur naam `.env` rakho:

```ini
FLASK_SECRET_KEY=koi-lamba-random-text
PORT=5000
MAX_UPLOAD_MB=20

LOCAL_AI_PORT=8080
LOCAL_AI_CONTEXT=8192
# Doosra model (GGUF ka direct link) chahiye to:
# LOCAL_AI_MODEL_URL=https://huggingface.co/.../model.gguf
```

- `PORT=5001` → app `http://127.0.0.1:5001` par chalega.
- `.env` badalne ke baad app restart karo.
- Model upgrade karna ho to `models/` folder se purani `.gguf` file delete karo aur `LOCAL_AI_MODEL_URL` set karke app dobara chalao.

---

## Advanced: pehle se chal raha model server use karna

Agar aapke paas **Ollama** ya **LM Studio** already chalta hai, to app use khud detect kar leti hai — kuch karne ki zaroorat nahi. Force karna ho:

```ini
# Ollama ke liye
LLM_BACKEND=ollama
OLLAMA_MODEL=qwen2.5:1.5b

# LM Studio / Bionic / kisi bhi local OpenAI-compatible server ke liye
LLM_BACKEND=openai
OPENAI_BASE_URL=http://127.0.0.1:1234/v1
```

---

## Aapka data aur backup

| Cheez | Kahan |
|---|---|
| Database (accounts, summaries, embeddings) | `instance/demo.sqlite3` |
| Original PDFs | `instance/uploads/<paper-id>/` |
| AI runtime + model (delete kar sakte ho) | `runtime/`, `models/` |
| Model server log | `logs/local-ai.log` |

Backup: app band karke poora **`instance`** folder copy kar lo. Purana Supabase data apne aap nahi aayega — naya account banao aur PDFs dobara upload karo.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python is not recognized` | Python install karte waqt PATH tick nahi hua — installer → Modify → PATH add → PC restart |
| Terminal: "The local model server did not start" | `logs/local-ai.log` ki last lines dekho; antivirus ko `runtime/llama/llama-server.exe` allow karo |
| Download beech mein ruk gaya | `start.bat` dobara chalao — adhoora file `.part` delete karke phir se download hoga |
| Footer: "Preview mode" | Model server band hai. Terminal band hua tha? `start.bat` dobara chalao. |
| Summary bahut slow | Chhoti PDF se test karo, background apps band karo. Bade model (3B) se slow hoga. |
| `Address already in use` | `PORT=5001 python local_ai.py` (PowerShell: `$env:PORT=5001; python local_ai.py`) |
| Antivirus/SmartScreen warning | "More info → Run anyway"; ya manual commands (Step 3 ka mac/Linux wala block) |
| Password bhool gaye | Login page → Forgot password (code screen par hi dikhta hai). Sab reset karna ho to app band karke `instance/` delete karo. |
| Scanned PDF ka error | OCR add-on install karo: `.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt` (phir app restart). Default 20 pages tak OCR hota hai (`OCR_MAX_PAGES`) |
| Disk space kam | `models/` delete karo (space free hoga); agli baar phir download hoga |

---

## Scanned / image PDF padhna (optional)

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
```

Isse `pypdfium2` + `rapidocr-onnxruntime` + `pdfplumber` install hote hain (Tesseract ki zaroorat nahi, models package ke andar aate hain). Uske baad image-only PDF bhi automatic OCR ho jati hai, aur **paper ke tables Markdown** ban kar store hote hain (isliye "accuracy kitni thi" jaise sawaal par numbers sahi aate hain). Equations `formula` tag ke saath store hoti hain aur numbers/table wale sawaal par priority milti hai. Table parsing band karni ho to `TABLE_EXTRACTION=false`. — pages ki limit `OCR_MAX_PAGES` (default 20) se badal sakte ho, ya `OCR_ENABLED=false` se band kar sakte ho. OCR thoda slow hota hai.

## Project documents (college/demo ke liye)

- `docs/OFFLINE_PRIVACY.md` — data kahan rehta hai, kya kabhi bahar jata hai, khud verify kaise karein
- `docs/PROJECT_SYNOPSIS.md` — poora synopsis (abstract, architecture, modules, limits)
- `DEMO_GUIDE.md` — 8–10 minute ka demo script (privacy proof ke saath)
- `PRESENTATION_CHECKLIST.md` — slides outline + expected questions ke jawab
- `README.md` — setup aur configuration

## Tests (optional)

```powershell
.\.venv\Scripts\activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Expected: **65 passed**. Tests koi model download ya network call nahi karte.

---

## Checklist

- [ ] ZIP extract kiya
- [ ] Python 3.10+ installed (PATH tick)
- [ ] `start.bat` chalaya (dependencies + model download hua)
- [ ] http://127.0.0.1:5000 khula
- [ ] Local account banaya
- [ ] Sample PDF ka summary generate hua
- [ ] Sawaal poocha aur page reference mila
- [ ] `instance/` folder ka backup liya

Ho gaya! Ab DocuQuery bilkul offline, bina API key, bina cloud ke aapke laptop par chalti hai.
