# DocuQuery — offline PDF research assistant

Upload a text-based research PDF, generate a structured brief, and ask questions with page references. Everything runs on your computer: Flask, PDF extraction, hashing embeddings, SQLite, and a small local language model. No API key, no account on any website, no cloud database.

The chat card also picks **paper-specific questions** for you. The moment a paper is
uploaded, *Try asking* shows questions built from its title, sections and key terms; the
local model then rewrites them in the background into sharper questions about that paper,
and each one disappears from the list once you have asked it.

## One-time setup

1. Install Python 3.10+ (on Windows tick **"Add python.exe to PATH"**).
2. Run the app:

   ```bash
   python local_ai.py
   ```

   On Windows you can double-click **`start.bat`**, which does the same thing.

On the **first run** `local_ai.py` prepares the small pieces by itself:

- a llama.cpp CPU runtime (~25 MB) into `runtime/`
- then it starts the web app at <http://127.0.0.1:5000>

**Models are never downloaded behind your back.** The model (400 MB – 2 GB) is fetched
only when *you* click one: **Profile → AI model → a preset**, or paste a Hugging Face
`.gguf` link in the same card. Until then the app opens normally and answers with exact
PDF quotes. As soon as a download finishes, `start.bat` starts the model server by
itself — no restart, no console commands.

You can still ask for a download up front with `python local_ai.py --model small`
(or `default` / `large`), or download only the files with `--download-only`.

### If you already run a model server

DocuQuery reuses one automatically, nothing else to configure:

- **Ollama** with the model installed (`ollama pull qwen2.5:1.5b`)
- **LM Studio**, **Bionic**, llama.cpp or Jan with a local server started

Force a backend with `LLM_BACKEND=ollama` or `LLM_BACKEND=openai` in `.env`.

## Privacy

See [docs/OFFLINE_PRIVACY.md](docs/OFFLINE_PRIVACY.md) for the full data-flow, the exact
files stored on disk, and commands to verify that only `127.0.0.1` sockets are used. Short
version: after the one-time setup download, nothing leaves the laptop — no cloud database,
no model API, no analytics, no CDN.

## Using it offline

After the first run, keep the files and start the app again with `python local_ai.py` (or `start.bat`). No internet is needed: the UI ships its own CSS, PDFs stay in `instance/`, and model requests go only to `127.0.0.1`.

Useful options:

```bash
python local_ai.py --download-only   # prepare the runtime + model, then exit
python local_ai.py --no-model        # start the app in preview mode
```

### Scanned PDFs (optional OCR)

Text-based PDFs work out of the box. For scanned or image-only PDFs install the optional
OCR add-on once:

```bash
python -m pip install -r requirements-ocr.txt
```

It adds `pypdfium2` (page rendering), `rapidocr-onnxruntime` (ONNX OCR, models bundled) and
`pdfplumber` (tables), so no Tesseract or Poppler install is needed and everything runs
offline. Pages without a text layer are recognised automatically; `OCR_MAX_PAGES`
(default 20) and `OCR_ENABLED=false` control it. OCR is slower than text extraction.

### Workspace behaviour

- **Page chips are links** — clicking `p. 173` under an answer opens the stored PDF at that page.
- **Chat survives a refresh** — each paper's thread is kept in the browser (`localStorage`,
  last 40 messages); "Clear chat" wipes it.
- **Honest status banner** — if the local model is not running, the workspace says so and warns
  that answers will be quoted passages instead of written text.
- **Upload summary line** reports what was indexed: passages, tables found, OCR pages read.

### Other languages

You can ask in Hindi, Spanish, French, German, Italian, Chinese and more. Two things happen:

1. **Retrieval translation** — if the question is not English, the local model translates it for
   the search step only, so an English paper still matches (`translate_query`).
2. **Answer language** — the prompt tells the model to reply in the language of the question and
   to keep `[p. N]` markers unchanged.

Honest limits: the 0.5B preset is mostly English; for Hindi or other languages pick
`default` (1.5B) or `large` (3B) with `python local_ai.py --model large`. Very low-resource
languages will be translated but answered shakily, and the stored paper text must be readable
(OCR/English text) for retrieval to find anything.

### Asking for questions

The chat offers twelve one-click questions: six on the first row (Objective, Methods,
Dataset, Findings, Limits, Exam questions) and six behind **+ 6 more** (Key terms, Formulas,
Tables, Comparison, MCQ quiz, Viva questions). They are ordinary prompts, so you can always
type your own wording; `QUESTION_COUNT` (default 8) and `MCQ_COUNT` (default 5) set how many
questions the generator writes.


"Give me 8 exam questions from this paper" is handled by a dedicated prompt: the app samples
passages across the whole paper (not just the nearest four), asks the model to write
short- and long-answer questions, and tags each with its page marker. The `Exam questions`
chip in the chat does the same in one click. `QUESTION_COUNT` sets the default number.

Answers are also cleaned up: bracketed numbers copied from the paper's own reference list
(`[33.31]`) are removed, so only real page citations such as `[p. 173]` remain.

### Tables and equations

With `pdfplumber` installed, every paper table is stored as a **Markdown table** chunk
(`kind="table"`) instead of loose words, so questions like "what accuracy did they report?"
retrieve the real numbers and cite the page. Symbol-heavy equations are tagged
`kind="formula"`; when the question mentions numbers, tables or equations these chunks get a
small retrieval boost. `TABLE_EXTRACTION=false` disables table parsing. Formulas are quoted
as text (LaTeX is not rendered) — the model explains them in plain words.

### Which models show up (and where to add more)

The workspace chat card shows a **model chip** — it names the model that is answering and
turns amber when nothing is loaded. Click it to switch instantly; the full picker (with
hardware advice and download state) is on the Profile page.

The list is built from what is actually on the laptop:

| Source | How it gets there |
|---|---|
| Built-in presets | click one in Profile → AI model (or `python local_ai.py --model small\|default\|large`) |
| `models/` folder | drop any `.gguf` in it |
| **LM Studio** | its own model library is scanned automatically |
| **Ollama** | GGUF blobs in `~/.ollama/models` are offered as `qwen2.5:1.5b (Ollama)` |
| Bionic | `~/.bionic/models` |
| Any folder | set `EXTRA_MODEL_DIRS="D:\models;E:\gguf"` before `start.bat` |

Models installed by another app therefore appear on their own — no re-download. Switching from
the chip saves the choice; `start.bat` loads it next time.

Presets that are not on disk show **click to download** — clicking starts the download inside the
app (progress is shown on the chip, `POST /api/models/download` + `GET /api/models/download`), and
the finished model becomes the selected one.

### Adding any other model

Two ways, both end with the file inside the app's `models/` folder and the model selected:

| Way | Steps |
|---|---|
| **From a link** (Profile → AI model → *Add another model from a link*) | Hugging Face model page → **Files** → click the `.gguf` size → **Download** → copy that link → paste it in the app → **Download** |
| **From disk** | Profile → AI model → **Open folder** (or open `models/` yourself), drop the `.gguf` in, reload the page — it appears in the list |

A linked download is streamed into `models/` as `<name>.gguf.part` and only renamed to `.gguf` when it
finishes, so an interrupted download never looks like a working model. `POST /api/models/download-url`
accepts `http(s)` links only, rejects anything that does not start with the GGUF magic bytes, checks
free disk space first, and strips path separators from the file name so a link cannot write outside the
models folder. When the app was started by `start.bat`, the supervisor notices the new selection and
swaps the model within a couple of seconds — no restart.

### Model choice: automatic, saved, or switched from the app

DocuQuery looks at the laptop's RAM and marks the best fit (it does not download it for you):

| RAM | Picked automatically |
| --- | --- |
| under 7 GB | Qwen2.5 0.5B |
| 7–13 GB | Qwen2.5 1.5B |
| 14 GB or more | Qwen2.5 3B |

It also scans the computer for GGUF files you already downloaded, including the
**LM Studio** library (`~/.lmstudio/models`). See what is available with:

```bash
python local_ai.py --list-models
```

Then either pass a choice, or open **Profile → AI model** in the app, pick one and
click **Use selected model**. When the app was started by `start.bat` /
`local_ai.py`, the model server is swapped in the background — no restart needed.
Otherwise the choice is saved and applied on the next start.

```bash
python local_ai.py --model small
python local_ai.py --model-path "C:\Users\you\.lmstudio\models\qwen\qwen.gguf"
EXTRA_MODEL_DIRS="D:\models" python local_ai.py --list-models
```

### How long are the answers?

Answers default to a **balanced** length (roughly 120–250 words). The chat box has a
length switch next to **Clear**:

| Choice | Roughly | Good for |
| --- | --- | --- |
| Short | under 80 words | quick facts, page lookups |
| Balanced | 120–250 words | normal questions |
| Detailed | 300–450 words | explanations, comparing results, caveats |

Set a default in `.env` with `ANSWER_DETAIL=detailed`, or cap the length with
`ANSWER_MAX_TOKENS`. Longer answers take proportionally longer on a CPU — and small
models drift more when asked for long text, so check the citations.

### What changes with a different model?

| Model | Speed on a laptop CPU | Wording | Reliable citations | Best for |
| --- | --- | --- | --- | --- |
| Qwen2.5 0.5B | fastest (~20–40 tok/s) | simple sentences | sometimes wrong page numbers | quick lookups, low-RAM laptops |
| Qwen2.5 1.5B | medium (~8–15 tok/s) | coherent, structured | usually correct | default for 8 GB laptops |
| Qwen2.5 3B | slow (~4–8 tok/s) | closest to a good assistant | best of the three | 16 GB laptops, careful reading |

A **coder** model (`Qwen2.5-Coder`) is tuned for programming, so its prose about a
research paper is noticeably weaker — prefer the plain `Instruct` models.

### Choosing a model speed

| Preset | Command | Notes |
| --- | --- | --- |
| `small` | `python local_ai.py --model small` | Qwen2.5 0.5B, ~400 MB, fastest, 2-4x quicker answers |
| `default` | `python local_ai.py` | Qwen2.5 1.5B, ~1 GB, balanced |
| `large` | `python local_ai.py --model large` | Qwen2.5 3B, ~2 GB, better answers, roughly 2x slower |

With a GPU (even integrated Intel/AMD), use the Vulkan build for a large speed-up:

```bash
python local_ai.py --gpu
```

Delete the `runtime/` folder first if you switch to `--gpu`, so the Vulkan build is downloaded.

You can also tune speed in `.env`: `RAG_TOP_K` (default 4), `SUMMARY_CONTEXT_CHARS` (default 9000), `LOCAL_AI_CONTEXT` (default 6144), `LOCAL_AI_THREADS`.

No GPU is required, but CPU speed, RAM, and PDF size affect how fast summaries appear. If the model is missing or the server is down, DocuQuery still extracts and shows citation-linked passages instead of generated text. Scanned PDFs without selectable text need OCR before upload.

## Configuration and local data

Copy `.env.example` to `.env` to change settings. Highlights:

| Setting | Meaning |
| --- | --- |
| `LLM_BACKEND` | `auto` (default), `ollama`, or `openai` (any local OpenAI-compatible server) |
| `OLLAMA_MODEL` | model tag used when `LLM_BACKEND=ollama` |
| `OPENAI_BASE_URL` | local server URL, e.g. `http://127.0.0.1:1234/v1` |
| `LOCAL_AI_MODEL_URL` | use a different GGUF file for the built-in runtime |
| `LOCAL_AI_PORT` | port for the built-in model server (default `8080`) |
| `MAX_UPLOAD_MB` | upload limit in MB (default 40) |
| `FLASK_SECRET_KEY` | set a unique value for your installation |

Data lives next to the app:

- `instance/demo.sqlite3` — accounts, summaries, embeddings
- `instance/uploads/<paper-id>/` — the original PDFs
- `runtime/`, `models/` — the downloaded AI files (safe to delete to reclaim space; they download again)

Back up the whole `instance/` folder while the app is stopped. Existing SQLite data keeps working. Accounts and PDFs from the old Supabase version are **not** imported automatically; create a local account and upload the PDFs again.

This setup is for single-device use: keep Flask and the model server on loopback and do not expose them to your LAN or the internet.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use temporary databases and stubbed model replies; they never download a model or call a network service.

## Troubleshooting

- **"The local model server did not start"** — look at `logs/local-ai.log`. The last lines show the actual reason.
- **Antivirus blocks the downloaded runtime** — allow `runtime/llama/llama-server.exe`, or use LM Studio instead.
- **Download fails on a restricted network** — use LM Studio/Ollama and set `LLM_BACKEND=openai` or `ollama` in `.env`.
- **Port already in use** — run with `PORT=5001 python local_ai.py`.
