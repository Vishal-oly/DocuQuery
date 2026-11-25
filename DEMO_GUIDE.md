# Demo Guide — DocuQuery (offline, on-device)

A 8–10 minute demo that shows the paper workflow **and** proves nothing leaves the laptop.
Audience takeaway: *"It reads the paper on my machine, answers with page citations, and
still works with the internet switched off."*

## 0. One-time preparation (do this a day before)

1. `start.bat` (or `python local_ai.py`) — let the model download finish once.
2. Create an account, upload `examples/sample_scientific_article.pdf`, generate a summary
   and ask two questions. This warms the model into RAM and proves the flow.
3. Keep the PDF handy; a second, smaller PDF is useful as a backup.
4. Optional: `python local_ai.py --model small` if the demo laptop is slow.

## 1. Opening (1 minute)

Say:

> "DocuQuery reads scientific PDFs on the laptop itself. The paper, the index and the
> language model stay on this device. There is no cloud account, no API key and no upload
> to a server — I'll prove that at the end by turning the internet off."

Show the landing page: the **"100% ON-DEVICE"** tag and the *Private by design* section.

## 2. The problem (1 minute)

> "Reading a 12-page paper takes an hour. Chatbots summarise fast but upload the PDF,
> invent details, and rarely tell you the page a claim came from."

Show a summary from a generic chatbot (prepared screenshot) with no citations, then say
DocuQuery does the same task with page-level evidence.

## 3. Upload and summary (3 minutes)

1. Log in → **Workspace** → upload the sample PDF.
2. Point at the pipeline: validated → text extracted page by page → passages indexed.
3. Click **Generate summary** (say it takes 20–60 s on a CPU; the first run is slowest).
4. When it appears, walk through **Objective / Methodology / Dataset / Findings /
   Limitations / Conclusion** and highlight the `[p. 4]` style citations.
5. Click a page chip → the original PDF opens at that page. This is the "trust" moment.

## 4. Ask the paper (2 minutes)

1. Ask: *"What dataset was used and how large was it?"*
2. Point at the answer plus **Evidence** chips.
3. Change the chat length switch to **Detailed** and ask:
   *"Summarise the limitations in detail."* — longer answer, same citations.
4. Ask something out of scope, e.g. *"What is the population of India?"* — the app says the
   excerpts do not contain it. This shows it is grounded, not a general chatbot.

## 5. Switch model (1 minute, optional)

Profile → **AI model** → show the list (0.5B / 1.5B / 3B plus models found on disk, with
the recommendation based on RAM) → choose one → **Use selected model**.

> "The app picked 1.5B because this laptop has 8 GB RAM. If the demo machine is slow I can
> switch to 0.5B live; if someone has 16 GB they can use 3B for better wording."

## 6. Privacy proof (1–2 minutes)

This is the part that lands the project.

1. Turn off Wi-Fi / unplug the cable (or enable airplane mode).
2. Reload the page and ask another question — it still answers.
3. Open PowerShell:
   ```powershell
   Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 5000,8080 }
   ```
   Both rows show `127.0.0.1`.
4. Open DevTools → Network → reload: every request is `127.0.0.1:5000`, no CDN, no fonts.

Close with:

> "One download at setup, then the whole system is on this laptop. That is why it is safe
> for unpublished work."

## Fallback plans

| Situation | What to do |
| --- | --- |
| Model too slow on the demo laptop | Start with `--model small`, or demo with the summary already generated and only ask one short question |
| Model server crashed | Restart `start.bat`, wait for "Model ready", continue. Answers fall back to retrieved passages meanwhile, which still demonstrates citations |
| No GPU / weak CPU | Keep answers Short, avoid Detailed |
| Projector, no audio | Everything is visual; no video needed |
| Forgot the password | New account in 20 seconds; demo data can be re-uploaded |

## What to emphasise in questions

- **Why local?** Confidential or unpublished papers, offline labs, exam halls, no API cost.
- **Why small models?** They fit on a normal laptop; the app shows citations so the reader
  can verify, and the model can be swapped.
- **Why SQLite?** One file, no server, easy backup, per-account scoping.
- **What about accuracy?** Grounded retrieval + page citations + extractive fallback; small
  models are verified by the reader, not trusted blindly.
- **How is it engineered?** `pdf_processing`, `repository`, `rag`, `llm`, `model_registry`,
  `local_ai.py` supervision — see `docs/PROJECT_SYNOPSIS.md`.
