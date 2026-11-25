# Naya model install karna — step by step

Model ek `.gguf` file hoti hai jo app ke `models\` folder me save hoti hai. **Ek baar download → phir hamesha offline chalta hai.** `start.bat` khud koi model download nahi karta; model tum app ke andar se laate ho.

---

## Tarika 1 — App ka apna model (sabse aasan, recommended)

1. **`start.bat` double-click** karo aur window ko band mat karo (minimize kar do).
2. Browser me kholo: **http://127.0.0.1:5000** → login karo.
3. Top-right me apne naam par click → **Profile**.
4. **AI model** card me list dikhegi:
   ```
   ○ Qwen2.5 0.5B Instruct   400 MB · built-in · recommended
   ○ Qwen2.5 1.5B Instruct   1000 MB · built-in
   ○ Qwen2.5 3B Instruct     2000 MB · built-in
   ```
5. Jo chahiye uske aage wala **gol button (radio)** select karo.
6. Neeche **Use selected model** dabao → download turant shuru:
   ```
   Downloading Qwen2.5 3B Instruct — 42% of 2000 MB
   ```
7. Poora hone par line badal jayegi: **"… is saved and selected."** — aur model **apne aap start** ho jayega (10–30 second). Restart ki zaroorat nahi.
8. Check karne ke liye chat card me model chip dekho: **`Qwen2.5 3B` · running · offline**. Footer me bhi **"Local model ready"** dikhega.

> Pehla jawab hamesha slow hota hai (model RAM me load hota hai) — 20–60 second normal hai. Uske baad tez.

### Kaunsa model chunein

| Laptop RAM | Model | Size | Feel |
|---|---|---|---|
| 4–6 GB | Qwen2.5 **0.5B** | ~400 MB | sabse tez, quality basic |
| 8 GB (zyadatar laptops) | Qwen2.5 **1.5B** | ~1 GB | **best balance — isi se shuru karo** |
| 16 GB | Qwen2.5 **3B** | ~2 GB | better answers, thoda slow |

Disk me **2x jagah** rakho (download ke waqt `.part` file bhi banti hai): 3B ke liye ~4 GB free.

---

## Tarika 2 — Hugging Face se koi bhi doosra model (link se)

App kisi bhi GGUF model ko link se la sakta hai.

1. Browser me model ka page kholo, jaise:
   `https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF`
2. **Files and versions** tab kholo.
3. File chuno — naam me **`Q4_K_M`** wala sabse best balance hai (jaise `qwen2.5-7b-instruct-q4_k_m.gguf`).
4. Us file ke aage **size** (jaise `4.68 GB`) par click karo → download page khulega.
5. **Download** button par **right-click** → **Copy link address**.
6. App me → **Profile → AI model** → *Add another model from a link* box me link **paste** karo → **Download**.
7. Progress wahin dikhega: `Downloading the model — 12% of 4680 MB`.
8. Khatam hone par: **"… is saved and selected"** → model khud start.

| Quant | Size (7B) | Kab |
|---|---|---|
| `Q4_K_M` | ~4.5 GB | **default choice** |
| `Q5_K_M` | ~5.5 GB | thoda better, zyada RAM |
| `Q3_K_M` | ~3.5 GB | kam space, quality kam |

> 7B model ke liye kam se kam **8 GB RAM** chahiye (16 GB better). 8 GB laptop pe 3B se aage mat jao — jawab dheere aur garm hoga.

---

## Tarika 3 — Model pehle se laptop me hai (dobara download nahi)

LM Studio / Ollama se pehle download kiya hua model app khud list kar leta hai:

1. **Profile → AI model** → list me neeche dekho: **"GGUF files on this laptop"** section.
2. Wahan `qwen2.5:1.5b (Ollama)` ya LM Studio ka model dikhega → select → **Use selected model**.

Manual file daalni ho:

1. Profile me **Models are saved in** ke aage path dikhta hai — **Open folder** dabao.
2. Us folder me apni `.gguf` file **copy-paste** karo.
3. Browser me **F5** (refresh) → list me naam aa jayega → select → **Use selected model**.

Alag folder se padhna ho (jaise `D:\models`) to `start.bat` se pehle ek baar:
```bat
set EXTRA_MODEL_DIRS=D:\models
start.bat
```

---

## Model badalna (baad me kabhi bhi)

- **Chat card** me model chip (naam wala button) click karo → **Recommended presets** / **GGUF files on this laptop** list khulegi → jo chahiye uspe click.
- Download hua model turant switch ho jata hai (kuch second ruk kar jawab dena).
- Jo model pehle se nahi hai, uspe **"click to download"** likha hoga — click = download shuru.

---

## Purana model hatana (disk free karna)

1. Profile → **Open folder**.
2. `.gguf` file delete karo (jo hatana hai).
3. Page refresh → list se gayab. `selected.json` ko chhedne ki zaroorat nahi.

---

## Kuch galat ho to

| Dikhta kya hai | Matlab / kya karo |
|---|---|
| `Download failed — check your internet connection` | Net off ya link galat. Model pe dobara click karo, ya link phir copy karo |
| `That link is not a GGUF model file` | HTML page ka link copy hua hai — Files tab se `.gguf` file ka link lo |
| `Not enough disk space` | Jagah free karo (3B ke liye ~4 GB) |
| Download 100% par atak gaya | `.part` file delete karo (`models\` folder) aur dobara click — poora hone par hi `.gguf` banta hai |
| Chip: `no model yet · Profile` | Model download nahi hua / start nahi hua → Profile se download karo |
| Jawab sirf PDF ke quotes aa rahe hain | Model load nahi hua; 20–30 second ruko, phir naya sawaal poocho |
| Bahut slow | Chhota model (1.5B) chuno, ya `Detailed` ki jagah `Short` rakho |

---

## Terminal wala raasta (optional, UI chhod kar)

```powershell
.venv\Scripts\python.exe local_ai.py --model small     # 0.5B  ~400 MB
.venv\Scripts\python.exe local_ai.py --model default   # 1.5B  ~1 GB
.venv\Scripts\python.exe local_ai.py --model large     # 3B    ~2 GB
.venv\Scripts\python.exe local_ai.py --list-models     # kya-kya pada hai
.venv\Scripts\python.exe local_ai.py --model-path "C:\models\my.gguf"
```
Ye command model ko download + start dono karti hai. `start.bat` par koi asar nahi — wo phir bhi bina download khulta hai.
