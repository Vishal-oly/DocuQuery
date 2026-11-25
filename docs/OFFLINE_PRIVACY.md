# Offline operation and privacy

DocuQuery runs on one laptop. There is no server somewhere else, no account on a
website, and no API key. This page explains exactly what runs where, what is stored,
what leaves the machine (only the first-time download), and how to verify all of it
yourself.

## Short version

| Question | Answer |
| --- | --- |
| Where does the language model run? | On your CPU/GPU, via `llama.cpp` started by `local_ai.py` (or an Ollama / LM Studio server you run yourself) |
| Where are PDFs and summaries stored? | `instance/` inside the project folder, on your disk |
| Is anything sent to Groq, OpenAI, Supabase or Google? | No. Those integrations were removed from the code |
| Does the app need an account on a website? | No. Accounts are email + password rows in your local SQLite file |
| Any analytics, telemetry or third-party CDN? | No. The UI uses local CSS/files and local icons |
| Does it need internet? | Only for the first run (Python packages + ~1.1 GB model download). After that, none |

## What happens on the first run

1. `pip install` fetches Python packages from PyPI.
2. `local_ai.py` downloads a llama.cpp CPU/Vulkan build (about 25–40 MB) from GitHub releases.
3. It downloads the Qwen2.5 GGUF model (about 0.4–2 GB depending on the preset) from Hugging Face.
4. It starts the model server on `127.0.0.1:8080` and the Flask app on `127.0.0.1:5000`.

Those three downloads are the only outbound connections the project makes. You can
list them in `local_ai.py` (`LLAMA_API`, `PRESETS[...]["url"]`) and in
`requirements.txt`.

## What is stored on disk

| Path | Contents |
| --- | --- |
| `instance/demo.sqlite3` | accounts (salted password hashes), papers, chunks, embeddings, summaries, chat history |
| `instance/uploads/<paper-id>/` | the original PDF files |
| `models/` | downloaded GGUF model files |
| `runtime/` | the llama.cpp binaries |
| `logs/` | model server output |
| `.env` | optional local settings (secret key, ports, model choice) |

Nothing in that list is synchronised anywhere. Copy the `instance/` folder to back it up.

## Data flow of one question

```
Browser (localhost)  →  Flask on 127.0.0.1:5000
                          ↓  retrieve matching chunks from SQLite
                          ↓  POST http://127.0.0.1:8080/v1/chat/completions
                       llama.cpp server on the same laptop
                          ↓  generated text
Browser shows the answer + page citations
```

Every arrow stays inside the machine. The HTTP calls use `127.0.0.1`, and the client in
`docuquery/llm.py` ignores proxy environment variables, so a corporate proxy is never
used for model traffic.

## Verify it yourself

1. **Airplane mode.** Finish setup once, then disconnect Wi-Fi / unplug the network
   cable. Upload a PDF, generate a summary and ask a question — it all still works.
2. **Look at the sockets.** In PowerShell:
   ```powershell
   Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 5000,8080 }
   ```
   Both should show `LocalAddress` `127.0.0.1`, never `0.0.0.0`.
3. **Watch the browser.** Open DevTools → Network, reload the app: every request goes to
   `127.0.0.1:5000`. There are no requests to CDNs or fonts.
4. **Grep the code.**
   ```powershell
   Select-String -Path docuquery\*.py -Pattern "https?://" -AllMatches
   ```
   The only URLs are the loopback addresses.
5. **Resource Monitor.** While a summary is generating, `llama-server.exe` uses the CPU/GPU;
   no other network traffic appears.

## Optional components

- **OCR add-on** (`requirements-ocr.txt`): `pypdfium2` + `rapidocr-onnxruntime` read scanned
  pages. Both are installed from PyPI once and then run offline; recognised text is stored
  in the same local SQLite file.
- **Table extraction** (`pdfplumber`, included in the same optional file): turns paper tables into
  local Markdown chunks. No network use.
- **Optional embedding model** (`requirements-embeddings.txt`): stronger semantic search,
  downloaded once from Hugging Face.

Neither component sends your documents anywhere.

## Honest limits

- **Disk is not encrypted.** Anyone who can log into your Windows account and open the
  project folder can read the PDFs and the database. Use BitLocker/FileVault and a
  Windows login if the laptop is shared.
- **Local accounts are simple by design.** Email + password with salted hashes, no email
  verification, no rate limiting, no two-factor. It is meant for one person on one laptop.
- **Keep it on loopback.** Do not run it with `HOST=0.0.0.0` on public Wi-Fi; that would
  expose the demo login to the network.
- **The model can still be wrong.** Local means private, not infallible. Small models can
  misread or mis-cite; always check the highlighted page.
- **External model servers are your choice.** If you point the app at Ollama or LM Studio,
  those tools run locally too — but check their own settings (some have optional cloud
  features) if you care about a strict no-network setup.
- **First run needs internet.** Without it, the app still starts in preview mode: upload,
  extraction and citation previews work, only generated text is missing.

## Checklist before a demo or submission

- [ ] Model downloaded (`models/*.gguf`) and a summary generated once
- [ ] Internet switched off, app still answers
- [ ] `Get-NetTCPConnection` shows only `127.0.0.1`
- [ ] No `.env` file with old cloud keys left in the folder
- [ ] `instance/` backed up, demo PDF re-uploaded if the folder was reset
