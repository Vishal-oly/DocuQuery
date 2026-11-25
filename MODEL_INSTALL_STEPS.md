# Installing a Model

DocuQuery runs a local GGUF model on your own computer. The model is a single file that is
stored in the `models\` folder and downloaded **once**; after that the application works
completely offline.

`start.bat` does not download a model. Models are added from inside the application, so you
stay in control of what is fetched and when.

---

## 1. In-app presets (recommended)

1. Double-click **`start.bat`** and keep the window open (minimise it; do not close it).
2. Open **http://127.0.0.1:5000** and sign in.
3. Select your name in the top-right corner, then **Profile**.
4. In the **AI model** card, choose a model from the list:

   | Option | Size | Notes |
   |---|---|---|
   | Qwen2.5 0.5B Instruct | 400 MB | fastest, basic quality |
   | Qwen2.5 1.5B Instruct | 1 GB | balanced — recommended starting point |
   | Qwen2.5 3B Instruct | 2 GB | better answers, slower on CPU |

5. Select the radio button next to the model you want.
6. Press **Use selected model**. The download starts immediately and progress is shown in place:

   ```
   Downloading Qwen2.5 3B Instruct — 42% of 2000 MB
   ```

7. When the download finishes, the message changes to **"… is saved and selected"** and the
   model server starts automatically. No restart is required.
8. Confirm the status in the chat card: the model chip should read **`Qwen2.5 3B · running · offline`**
   and the footer should show **"Local model ready"**.

> The first answer after loading is always slower, because the model is read into memory.
> 20–60 seconds is normal; subsequent answers are considerably faster.

### Choosing a model size

| System memory | Model | Download | Expected behaviour |
|---|---|---|---|
| 4–6 GB | Qwen2.5 0.5B | 400 MB | quickest; suitable for page lookups |
| 8 GB | Qwen2.5 1.5B | 1 GB | best balance of speed and quality |
| 16 GB or more | Qwen2.5 3B | 2 GB | fuller answers; noticeably slower |

Allow roughly twice the download size in free disk space, because the file is first written as
`.part` and renamed on completion (3B needs about 4 GB free).

---

## 2. Any GGUF model from Hugging Face

The application can download any model that is published as a `.gguf` file.

1. Open the model page, for example
   `https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF`.
2. Open the **Files and versions** tab.
3. Choose a quantisation. `Q4_K_M` is the usual balance of size and quality
   (for example `qwen2.5-7b-instruct-q4_k_m.gguf`).
4. Click the **file size** next to that file (for example `4.68 GB`) to open the download page.
5. Right-click **Download** and choose **Copy link address**.
6. In DocuQuery, open **Profile → AI model → Add another model from a link**, paste the link
   and press **Download**.
7. Progress appears beneath the field: `Downloading the model — 12% of 4680 MB`.
8. On completion the model is saved in `models\`, selected, and started automatically.

| Quantisation | Size (7B model) | When to use |
|---|---|---|
| `Q4_K_M` | ~4.5 GB | standard choice |
| `Q5_K_M` | ~5.5 GB | slightly better quality, more memory |
| `Q3_K_M` | ~3.5 GB | limited disk or memory, lower quality |

A 7B model requires at least 8 GB of memory (16 GB is comfortable). On an 8 GB laptop, a 3B
model is the practical upper limit.

---

## 3. A model that is already on your computer

Models downloaded by other tools are detected automatically.

1. Open **Profile → AI model** and scroll to **"GGUF files on this laptop"**.
2. LM Studio and Ollama models appear here (for example `qwen2.5:1.5b (Ollama)`).
3. Select one and press **Use selected model**. Nothing is downloaded again.

To add a file manually:

1. In the same card, press **Open folder** next to the models path.
2. Copy your `.gguf` file into that folder.
3. Refresh the page (**F5**). The model appears in the list; select it and press **Use selected model**.

To read models from another folder, set the variable before starting the application:

```bat
set EXTRA_MODEL_DIRS=D:\models
start.bat
```

---

## 4. Switching models later

- Open the chat card and click the **model chip** to see all available models.
- Presets that are not downloaded are labelled **"click to download"**; clicking one starts the download.
- Models already on disk switch immediately; the server restarts in the background, so answers
  may pause for a few seconds.

## 5. Removing a model

1. Open **Profile → AI model** and press **Open folder**.
2. Delete the `.gguf` file you no longer need.
3. Refresh the page; the entry disappears from the list.

The saved selection file (`selected.json`) does not need to be edited.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| *Download failed — check your internet connection* | Network unavailable or link expired | Click the model again, or copy the link afresh |
| *That link is not a GGUF model file* | A web page was copied instead of the file | Open **Files** on Hugging Face and copy the `.gguf` link |
| *Not enough disk space* | Insufficient free space for the download | Free space (about 4 GB for a 3B model) and retry |
| Download stops at 100% | The file was not finalised | Delete the `.part` file in `models\` and download again |
| Answers contain only PDF quotations | No model is loaded yet | Wait 20–30 seconds after the download, then ask again |
| Chip reads *no model yet · Profile* | No model downloaded or started | Open **Profile → AI model** and download one |
| Answers are slow | Model too large for this CPU | Choose the 1.5B model, or set the answer length to **Short** |

---

## Command-line reference (optional)

These commands download and start a model without using the interface:

```powershell
.venv\Scripts\python.exe local_ai.py --model small     # 0.5B   ~400 MB
.venv\Scripts\python.exe local_ai.py --model default   # 1.5B   ~1 GB
.venv\Scripts\python.exe local_ai.py --model large     # 3B     ~2 GB
.venv\Scripts\python.exe local_ai.py --list-models     # list what is installed
.venv\Scripts\python.exe local_ai.py --model-path "C:\models\my.gguf"
```

`start.bat` is unaffected by these commands: it always starts without downloading a model.
