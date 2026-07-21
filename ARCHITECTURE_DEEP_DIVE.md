# Architecture Deep Dive — HackVerse SIDBI Business Readiness Report

*Written for hackathon Q&A preparation. Based strictly on the actual codebase as of commit `8f8097b`.*

---

## Table of Contents

1. [Full Request Lifecycle](#1-full-request-lifecycle)
2. [Each Agent in Depth](#2-each-agent-in-depth)
3. [RAG Pipeline in Depth](#3-rag-pipeline-in-depth)
4. [Frontend State Machine](#4-frontend-state-machine)
5. [Full Environment Variable Map](#5-full-environment-variable-map)
6. [Deployment Pipeline](#6-deployment-pipeline)
7. [Failure Modes](#7-failure-modes)
8. [Glossary](#8-glossary)

---

## 1. Full Request Lifecycle

This trace follows a single `POST /report` call with **all three inputs provided** (photos, audio, CSV).

### Phase 1 — Browser → HTTP Request

**File:** `frontend/app/page.tsx`

1. User clicks "Generate Report" button
2. `handleSubmit()` (line 67) is called
3. A `FormData` object is built:
   ```
   FormData {
     "photos" -> File (photo1.jpg)
     "photos" -> File (photo2.jpg)
     "audio"  -> File (voicenote.wav)
     "transactions" -> File (transactions.csv)
   }
   ```
4. `fetch(API, { method: "POST", body: fd })` is called
   - `API` = `process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001/report"`

### Phase 2 — FastAPI Route Entry

**File:** `backend/app/main.py`

5. FastAPI receives the multipart request
6. `report()` (line 107) is entered
   - `photos: List[UploadFile] = File(None)` — parsed from multipart `photos` fields
   - `audio: UploadFile = File(None)` — parsed from multipart `audio` field
   - `transactions: UploadFile = File(None)` — parsed from multipart `transactions` field

### Phase 3 — Coroutine Construction (still sequential)

7. Timings dict created: `timings = {}`
8. Three coroutines are **constructed** (not awaited yet):
   ```python
   vision_coro = _run_agent("vision", photos, False, analyze_photos, timings)
   voice_coro  = _run_agent("voice", audio, True, process_voice, timings)
   txn_coro    = _run_agent("transactions", transactions, True, analyze_transactions, timings)
   ```
9. Only non-None inputs are gathered:
   ```python
   coros = [vision_coro, voice_coro, txn_coro]
   mapping = ["vision", "voice", "transactions"]
   ```

### Phase 4 — Concurrent Agent Execution

10. `await asyncio.gather(*coros)` — all three agents run **concurrently** in separate threads

Each `_run_agent()` call does:

11. Writes uploaded file(s) to temp files via `tempfile.NamedTemporaryFile`
12. Calls the handler function via `await asyncio.to_thread(handler, ...)` — runs in a thread pool so the async event loop is not blocked
13. Records timing in the `timings` dict *after* cleanup (in `finally` block)
14. Returns the agent result dict

Inside each thread:

- **Vision thread:** `vision_agent.py:analyze_photos(image_paths)` → OpenRouter API call(s)
- **Voice thread:** `voice_agent.py:process_voice(audio_path)` → Whisper (local CPU) → OpenRouter API call
- **Transaction thread:** `transaction_agent.py:analyze_transactions(csv_path)` → pandas CSV parsing (pure CPU, no API)

### Phase 5 — Result Classification

15. Loop over `zip(mapping, gathered)` assigns each result to `vision_result`, `voice_result`, `transaction_result`
16. Each result is classified as:
   - `None` → appended to `missing`
   - Dict containing `"error"` key → appended to `input_errors` with descriptive message
   - Otherwise → considered valid

### Phase 6 — RAG Retrieval (sequential, after agents)

**File:** `backend/app/rag/retrieve.py`

17. `t0 = time.time()`
18. `retrieve("MSME working capital lending guidance", k=3)` called
19. ChromaDB similarity search returns top-3 chunks
20. `timings["rag"] = round(time.time() - t0, 2)`

### Phase 7 — Synthesis (sequential, after RAG)

**File:** `backend/app/agents/synthesis_agent.py`

21. `t0 = time.time()`
22. All agent results + RAG context passed to `synthesize_report()`
23. Inside:
    - Evidence strings built from vision/voice/transaction results (or marked `[photos: missing]` / `[voice: missing]` / `[transactions: missing]`)
    - RAG context joined into a single string
    - Prompt sent to OpenRouter `ibm-granite/granite-4.1-8b`
    - LLM response parsed from markdown fences → JSON
    - `missing_inputs` list injected
24. `timings["synthesis"] = round(time.time() - t0, 2)`

### Phase 8 — Response Assembly

25. `main.py` merges:
    - `report_data["missing_inputs"] = missing`
    - `report_data["input_errors"] = input_errors`
    - `report_data["_timings"] = timings`
26. `print(f"[timings] {timings}", flush=True)` — logged to stdout
27. FastAPI returns the dict as JSON (200 OK)

### Phase 9 — Frontend Rendering

**File:** `frontend/app/page.tsx`

28. `handleSubmit()` awaits `res.json()` → `data: Report`
29. `setReport(data)`, `setScreen("report")`
30. React re-renders the report screen:
    - Business type card
    - Three `BandPill` components (revenue, inventory, digital)
    - Assessment box
    - Scheme note
    - Evidence summary bullet list
    - Missing inputs amber warning (conditional)

### Timing Summary

```
[timings] {'vision': 8.3, 'voice': 6.1, 'transactions': 0.4, 'rag': 0.1, 'synthesis': 5.2}
```

- Vision, voice, transactions run **concurrently** (wall time ≈ max of the three)
- RAG and synthesis run **sequentially** after agents complete
- Total wall time ≈ max(vision, voice, transactions) + rag + synthesis

---

## 2. Each Agent in Depth

### 2a. Vision Agent — `backend/app/agents/vision_agent.py`

#### Signature
```python
def analyze_photos(image_paths: list[str]) -> dict
```

#### Input
`image_paths`: list of absolute paths to JPEG/PNG files on local filesystem.

#### External API Calls

| Call | Model | Endpoint | Purpose |
|------|-------|----------|---------|
| 1 per image | `google/gemini-2.5-flash` | `https://openrouter.ai/api/v1/chat/completions` | Describe inventory, shop condition, activity |
| 1 summary call | `google/gemini-2.5-flash` | same endpoint | Cross-image comparison summary |

#### Output Shape
```json
{
  "per_image": [
    {
      "file": "photo1.jpg",
      "description": "Shelves stocked with packaged food products. A counter with a payment terminal visible. Two employees present."
    }
  ],
  "summary": "Both images show well-stocked retail shelves with consumer packaged goods. The payment terminal suggests digital payment acceptance."
}
```

#### Error Paths
- **File doesn't exist** → `open()` raises `FileNotFoundError` → caught by bare `except Exception` → prints error to stderr → `sys.exit(1)` **kills the uvicorn process**
- **OpenRouter API fails** (network error, invalid key, rate limit) → `client.chat.completions.create()` raises → caught → `sys.exit(1)` **kills the server**
- **Image is corrupt/unreadable** → `open()` succeeds but base64 decode may work; API may return error → same `sys.exit(1)`

#### Missing Input Behavior
If `photos` is `None`, `_run_agent` returns `None` without calling `analyze_photos`. The `report()` route appends `"photos"` to `missing`. The `synthesize_report()` function inserts `[photos: missing]` into the evidence string.

---

### 2b. Voice Agent — `backend/app/agents/voice_agent.py`

#### Signature
```python
def process_voice(audio_path: str) -> dict
```

#### Input
`audio_path`: absolute path to a WAV/MP3 audio file.

#### External API Calls

| Call | Model | Endpoint | Purpose |
|------|-------|----------|---------|
| 1 (local) | `faster-whisper` base (CPU int8) | N/A (local) | Speech-to-text transcription |
| 1 | `ibm-granite/granite-4.1-8b` | `https://openrouter.ai/api/v1/chat/completions` | Extract structured JSON from transcript |

#### Output Shape
```json
{
  "transcript": "i run a grocery store in chennai for about 10 years now we sell rice pulses and packaged items",
  "extracted": {
    "business_type": "grocery retail",
    "products": "rice, pulses, packaged items",
    "years_operating": "10",
    "location": "chennai"
  },
  "label": "officer observation, unverified"
}
```

#### Key Implementation Details
- **Whisper singleton** — `_whisper_model` is module-level, initialized once on first `process_voice()` call. Subsequent calls reuse the loaded model.
- **Per-step timing** — prints `[voice_agent] whisper transcribe took Xs` and `[voice_agent] openrouter extraction took Xs` to stdout.
- **Markdown fence stripping** — if the OpenRouter response wraps JSON in ` ```json ... ``` `, the fences are stripped before `json.loads()`.

#### Error Paths
- **Audio file missing** → Whisper `model.transcribe()` will raise → no try/except in `process_voice()` → exception propagates up through `asyncio.to_thread()` → caught by FastAPI as 500 error
- **Whisper model loading fails** → `_get_whisper()` raises → same propagation
- **OpenRouter call fails** → `or_client.chat.completions.create()` raises → no try/except → propagates up → 500 error
- **LLM returns non-JSON** → `json.loads()` raises `JSONDecodeError` → **caught by local try/except** → returns `{"raw_response": raw}` (graceful degradation)
- **Transcript is empty/silence** → Whisper returns empty segments → `" ".join(...)` produces empty string → OpenRouter gets empty transcript → likely returns `{}` → `json.loads("{}")` succeeds but `extracted` is empty dict

#### Missing Input Behavior
Same pattern as vision: `_run_agent` returns `None`, `missing` gets `"voice"`, synthesis inserts `[voice: missing]`.

---

### 2c. Transaction Agent — `backend/app/agents/transaction_agent.py`

#### Signature
```python
def analyze_transactions(csv_path: str) -> dict
```

#### Input
`csv_path`: absolute path to a CSV file.

#### External API Calls
**None.** This is a pure pandas/NumPy computation.

#### Output Shape
```json
{
  "total_inflow": 450000.00,
  "total_outflow": 320000.00,
  "transaction_count": 145,
  "average_transaction": 3103.45,
  "volatility": "moderate",
  "trend": "increasing"
}
```

Optional field (when no direction indicator is available):
```json
{
  "assumptions": ["all transactions treated as inflow — no direction indicator found in source data"]
}
```

#### Column Normalisation Logic

The agent handles these column name variants by normalising them to standard names (`date`, `type`, `amount`, `debit`, `credit`):

| Standard | Variants |
|----------|----------|
| `date` | `date`, `transaction_date`, `txn_date`, `dt`, `timestamp` |
| `type` | `type`, `transaction_type`, `txn_type`, `credit_debit`, `nature`, `debit_credit` |
| `amount` | `amount`, `amt`, `value`, `transaction_amount`, `txn_amount`, `amount_usd` (substring "amount" or "value" as fallback) |
| `debit` | `debit`, `dr`, `debit_amount`, `withdrawal`, `withdrawals` |
| `credit` | `credit`, `cr`, `credit_amount`, `deposit`, `deposits` |

#### Direction Inference Logic

Three scenarios:

1. **Separate debit/credit columns exist** → each row produces 1-2 rows (one debit, one credit) with explicit `type`
2. **Only amount column, mixed signs** → negatives become "debit", positives become "credit", amounts `.abs()`-ed
3. **Only amount column, all same sign** → if all negative: all "debit"; if all positive: all "credit" with `assumptions` note; if mixed signs: handled as case 2

#### Metric Calculations

- **`volatility`** — coefficient of variation (std/mean) of daily net amounts. Thresholds: `< 0.5` → low, `< 1.0` → moderate, `>= 1.0` → high
- **`trend`** — linear regression slope of monthly net totals. If slope magnitude > 5% of mean absolute monthly net → "increasing"/"decreasing", otherwise "stable"

#### Error Paths
- **CSV file missing** → `os.path.isfile()` check → returns `{"error": "transaction data unavailable"}`
- **`pd.read_csv()` fails** (malformed CSV, encoding issue) → caught → returns `{"error": "transaction data unavailable"}`
- **Empty CSV** → `df.empty` check → returns `{"error": "transaction data unavailable"}`
- **No date column** → explicit check → prints columns to stderr → returns `{"error": "transaction data unavailable"}`
- **No amount column** → `_find_amount_col()` returns `None` → prints columns to stderr → returns `{"error": "transaction data unavailable"}`
- **All amounts NaN after coercion** → `df.dropna(subset=["amount"])` yields empty → returns `{"error": "transaction data unavailable"}`
- **Division by zero in volatility** → `daily_net.mean() != 0` guard → `cv = 0.0`

---

### 2d. Synthesis Agent — `backend/app/agents/synthesis_agent.py`

#### Signature
```python
def synthesize_report(
    vision_result: dict | None,
    voice_result: dict | None,
    transaction_result: dict | None,
    rag_context: list[dict],
) -> dict
```

#### Inputs
- `vision_result`: output of `analyze_photos()` or `None` if missing/errored
- `voice_result`: output of `process_voice()` or `None`
- `transaction_result`: output of `analyze_transactions()` or `None`
- `rag_context`: list of `{"content": str, "source": str}` from `retrieve()`

#### External API Calls

| Call | Model | Endpoint | Purpose |
|------|-------|----------|---------|
| 1 | `ibm-granite/granite-4.1-8b` | `https://openrouter.ai/api/v1/chat/completions` | Synthesise all evidence into structured assessment |

#### Output Shape
```json
{
  "business_type": "grocery retail",
  "revenue_consistency_band": "Moderate",
  "inventory_observation_band": "Strong",
  "digital_activity_band": "Low",
  "relevant_scheme_note": "Based on SIDBI guidelines, micro-enterprises with a stable revenue stream may qualify for collateral-free loans up to ₹20 lakh under the MSME priority sector lending framework.",
  "assessment_band": "Suitable for micro-loan assessment",
  "evidence_summary": [
    "Photos show well-stocked retail shelves with digital payment terminal visible",
    "Business owner reported 10 years of operation in Chennai",
    "Transaction analysis shows moderate volatility and increasing trend over 12 months"
  ],
  "missing_inputs": []
}
```

#### Prompt Engineering

The system prompt enforces:
- No invented numeric scores or currency amounts
- Bands based only on provided evidence
- Favor "Further assessment required" when evidence is thin
- Strict JSON output with no markdown fences

The user prompt includes:
- Serialised JSON of each agent's output
- RAG context paragraphs
- Required JSON keys with allowed band values

#### Error Paths
- **Missing API key at module level** → `sys.exit(1)` on import — prevents server from starting
- **OpenRouter API call fails** → caught by bare `except Exception` → returns `{"error": "synthesis failed", "raw_response": None}`
- **LLM returns valid JSON but missing required keys** → No validation in synthesis_agent. Missing keys will be `undefined` in the response dict, causing potential frontend rendering issues.
- **LLM returns invalid JSON** → `json.loads()` raises → caught → returns error dict
- **`raw` variable not assigned** → `"raw" in dir()` check returns `False` → `raw_response` key gets `None`

---

## 3. RAG Pipeline in Depth

### 3a. Ingestion — `backend/app/rag/ingest.py`

#### Chunking Parameters
- **Splitter:** `RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)`
- Chunks are created from langchain `Document` objects (page text + metadata)

#### Embedding Method
**No explicit embedding step in user code.** The ChromaDB collection is created without a custom embedding function, so ChromaDB uses its **default ONNX embedding function**: `all-MiniLM-L6-v2` baked into the `chromadb` package. This is a lightweight ONNX Runtime-based embedding (~79MB download on first use, cached at `~/.cache/chroma/onnx_models/`).

#### Collection Info
- **Name:** `"sidbi_docs"`
- **Persistence:** `PersistentClient(path=chroma_db/)`
- **ID scheme:** UUID v4 for each chunk. **Deleted and recreated on each ingest run** (not additive).
- **Metadata stored:** `{"source": filename}` per chunk

#### Corpus Composition

| File | Pages | Chunks (approx) | Content |
|------|-------|-------|---------|
| `sidbi_direct_finance.pdf` | 21 | 33 | SIDBI direct finance scheme guidelines, loan limits, eligibility |
| `rbi_msme_master_direction.pdf` | 11 | ~25 | RBI Master Direction on lending to MSME sector — collateral requirements, priority sector targets, definitions |
| `sidbi_mudra_shishu_faq.pdf` | 8 | ~25 | SIDBI MUDRA Shishu loan FAQ — eligibility, loan amounts, repayment terms |

Total: **83 chunks from 40 pages** (as of last ingest).

### 3b. Retrieval — `backend/app/rag/retrieve.py`

#### Query Flow
1. `retrieve(query: str, k: int = 3)` is called (by `main.py` with query `"MSME working capital lending guidance"`)
2. ChromaDB collection is queried:
   ```python
   results = _collection.query(query_texts=[query], n_results=k)
   ```
3. ChromaDB embeds the query using the same ONNX `all-MiniLM-L6-v2` model
4. Cosine similarity search returns the top-k chunks with their metadata and distances

#### Result Formatting
```python
[
    {
        "content": "Chunk text extracted from PDF...",
        "source": "C:\\path\\to\\rbi_msme_master_direction.pdf"
    },
    ...
]
```
Note: `source` contains the absolute filesystem path (from `PyPDFLoader` metadata), not a relative path. This is a cosmetic issue — it doesn't affect functionality.

#### Module-Level Initialisation
```python
_client = chromadb.PersistentClient(path=CHROMA_DIR)
_collection = _client.get_collection(name="sidbi_docs")
```
This runs at import time. If ChromaDB doesn't exist or the collection hasn't been created yet, `get_collection()` raises `ValueError` → the module import fails → the server won't start. **Ingest must be run before the server.**

---

## 4. Frontend State Machine

### 4.1 React State Variables

| Variable | Type | Initial | Purpose |
|----------|------|---------|---------|
| `screen` | `"upload" \| "report"` | `"upload"` | Toggles between upload form and report view |
| `photos` | `File[]` | `[]` | Selected shop photo files |
| `audio` | `File \| null` | `null` | Selected voice note file |
| `csv` | `File \| null` | `null` | Selected CSV file |
| `loading` | `boolean` | `false` | Whether a request is in-flight |
| `report` | `Report \| null` | `null` | The structured report from the API |
| `error` | `string \| null` | `null` | Error message if fetch fails |

### 4.2 State Transitions

```
UPLOAD SCREEN
  │
  │ user selects files ──────────► photos[], audio, csv updated
  │                                (canSubmit = any is non-empty)
  │ user clicks × on photo ──────► photos.filter(...) removes that file
  │ user clicks "remove" on
  │   audio/csv ─────────────────► set to null, hidden input.value reset
  │
  │ user clicks "Generate Report"
  │ (disabled if !canSubmit)
  │   └─► setLoading(true)
  │       fetch(POST /report, FormData)
  │         │
  │         ├─ success ──────────► setReport(data), setScreen("report")
  │         │                       └─► REPORT SCREEN
  │         │
  │         └─ failure ──────────► setError(message), setLoading(false)
  │                                ("try again" button clears error)
  │
  │ while loading: spinner + "Analyzing evidence…" shown
  │
REPORT SCREEN
  │
  │ user clicks "New Report" ────► reset() clears all state → UPLOAD SCREEN
  │
  │ rendering:
  │   - Business type card (null → "Not specified")
  │   - 3× BandPill (revenue, inventory, digital)
  │   - Assessment box
  │   - Scheme note
  │   - Evidence summary list
  │   - Missing inputs amber note (conditional)
```

### 4.3 FormData Construction

```typescript
const fd = new FormData();
for (const f of photos) fd.append("photos", f);   // key "photos" appears multiple times
if (audio) fd.append("audio", audio);             // key "audio"
if (csv) fd.append("transactions", csv);           // key "transactions"
```

### 4.4 Response Rendering Logic

**`bandColor()`** — Maps `Band` to Tailwind classes:
- `"Low"` → `"bg-red-100 text-red-800"`
- `"Moderate"` → `"bg-yellow-100 text-yellow-800"`
- `"Strong"` → `"bg-green-100 text-green-800"`
- `default` → `"bg-slate-100 text-slate-800"` (fallback for unexpected values)

**Conditional rendering:**
- `report.business_type ?? "Not specified"` — null coalescing
- `(report.evidence_summary ?? []).map(...)` — defaults to empty array if missing
- `report.missing_inputs.length > 0` → amber warning box, with `.replace("photos", "shop photos").replace("voice", "voice note")` for readability

**`fetch` response handling:**
- `res.ok` check → if false, read body text and throw
- `res.json()` — if body is not valid JSON, throws `SyntaxError` → caught by generic `catch`
- `catch` — sets `error` to `err.message` or `"Unknown error"`

---

## 5. Full Environment Variable Map

| Variable | File | Line | Code | Missing Behaviour |
|----------|------|------|------|-------------------|
| `OPENROUTER_API_KEY` | `backend/app/agents/vision_agent.py` | 9 | `os.environ.get("OPENROUTER_API_KEY")` | `api_key` is `None` → `if not api_key` triggers `sys.exit(1)` |
| `OPENROUTER_API_KEY` | `backend/app/agents/synthesis_agent.py` | 10 | `os.environ.get("OPENROUTER_API_KEY")` | Same — `sys.exit(1)` on module load |
| `OPENROUTER_API_KEY` | `backend/app/agents/voice_agent.py` | 9 | `os.getenv("OPENROUTER_API_KEY")` | `OPENROUTER_API_KEY` is `None` → OpenAI client raises on first API call |
| `NEXT_PUBLIC_API_URL` | `frontend/app/page.tsx` | 5 | `process.env.NEXT_PUBLIC_API_URL \|\| "http://127.0.0.1:8001/report"` | Falls back to `localhost:8001` — works fine for dev |

### `.env.example` Contents
```
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

### Key Observations
- `HF_TOKEN` is no longer in `.env.example` (removed in commit `67fad01`) and is not read by any code
- `OPENROUTER_API_KEY` is the only required backend env var
- `NEXT_PUBLIC_API_URL` is the only frontend env var (and is optional)
- No `.env` file has ever been committed to git history

---

## 6. Deployment Pipeline

### Local Development

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate    # Windows
pip install -r requirements.txt
python -m app.rag.ingest     # One-time: create ChromaDB
uvicorn app.main:app --reload --port 8001

# Frontend
cd frontend
npm install
npm run dev
```

### Vercel (Frontend)

- **Build command:** `npm run build` (Next.js static export)
- **Env var to set:** `NEXT_PUBLIC_API_URL` = URL of the deployed backend
- **No special config file exists** — uses default Next.js Vercel deployment

### Render (Backend — not yet deployed)

Expected setup:
- **Start command:** `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8001`
- **Pre-deploy step:** Must run `python -m app.rag.ingest` as a one-time step (or as part of a build script) to populate ChromaDB
- **Cold start:** On Render free tier, the entire filesystem is ephemeral. Every cold deploy:
  - ChromaDB must be recreated (run ingest again)
  - ChromaDB ONNX model (~79MB) must be re-downloaded to `~/.cache/chroma/`
  - Whisper `base` model (~140MB on disk) must be re-downloaded on first `/report` call with audio
- **CORS:** Backend already allows `https://hack-verse-psi.vercel.app` as a production origin

### What Changes Between Environments

| Aspect | Local Dev | Vercel/Render |
|--------|-----------|---------------|
| Backend URL | `http://127.0.0.1:8001` | Set via `NEXT_PUBLIC_API_URL` |
| CORS origins | `http://localhost:3000` | `https://hack-verse-psi.vercel.app` |
| ChromaDB | Persistent on disk | Ephemeral — lost on restart |
| Whisper + ONNX models | Downloaded once, cached | Redownloaded on every cold start |
| File uploads | Stored in temp dir | Same (per-request temp files) |

---

## 7. Failure Modes

### Vision Agent

| Failure | What Happens | Severity |
|---------|-------------|----------|
| Image file can't be read | `sys.exit(1)` — **server dies** | Critical |
| OpenRouter API timeout | `sys.exit(1)` — **server dies** | Critical |
| OpenRouter returns unexpected response | `sys.exit(1)` — **server dies** | Critical |
| No photos uploaded | `_run_agent` returns `None`; synthesis uses `[photos: missing]` | Graceful |

### Voice Agent

| Failure | What Happens | Severity |
|---------|-------------|----------|
| Audio file missing/corrupt | Exception propagates → FastAPI 500 error | Degraded |
| OpenRouter fails | Exception propagates → FastAPI 500 error | Degraded |
| LLM returns non-JSON | Caught locally → `{"raw_response": raw}` returned | Degraded |
| Whisper fails to load model (OOM) | Exception → FastAPI 500 | Degraded |
| Audio is silent | Empty transcript → LLM gets empty string → likely returns `{}` | Silent wrong output |
| No audio uploaded | `_run_agent` returns `None`; synthesis uses `[voice: missing]` | Graceful |

### Transaction Agent

| Failure | What Happens | Severity |
|---------|-------------|----------|
| CSV file missing | Returns `{"error": "transaction data unavailable"}` | Graceful |
| Malformed CSV | `pd.read_csv()` fails → returns error dict | Graceful |
| No amount column found | Returns error dict with column list printed to stderr | Graceful |
| All amounts NaN | Returns error dict | Graceful |
| Unknown column names | Will likely miss amount column → returns error | Graceful |
| No transactions uploaded | `_run_agent` returns `None`; synthesis uses `[transactions: missing]` | Graceful |

### Synthesis Agent

| Failure | What Happens | Severity |
|---------|-------------|----------|
| API key missing | `sys.exit(1)` on import — **server won't start** | Critical |
| OpenRouter API fails | Returns `{"error": "synthesis failed", "raw_response": None}` | Degraded |
| LLM returns invalid JSON | Caught → returns error dict | Degraded |
| LLM returns valid JSON but missing keys | **No validation** — frontend renders undefined/blank values | Silent wrong output |
| LLM returns unexpected band value | `bandColor()` default case applies gray style | Cosmetic |

### RAG System

| Failure | What Happens | Severity |
|---------|-------------|----------|
| ChromaDB not populated (ingest never run) | `get_collection()` raises at import — **server won't start** | Critical |
| ChromaDB files corrupted | `PersistentClient()` may raise → server won't start | Critical |
| Query returns 0 results | `results["ids"][0]` — IndexError if code lacked guard; currently assumed `k>=1` always | Degraded |
| Large PDF corpus | More chunks → slower retrieval; no hard failure | Performance |
| ONNX model not cached (cold start) | First query downloads ~79MB → 5-15s latency | Performance |

### Frontend

| Failure | What Happens | Severity |
|---------|-------------|----------|
| Backend unreachable | `fetch` throws → error message displayed with "try again" | Graceful |
| Backend returns non-JSON | `res.json()` throws `SyntaxError` → caught → error displayed | Graceful |
| Backend returns 500 | `res.ok` is false → body text read and displayed | Graceful |
| `evidence_summary` is missing/undefined | `?? []` fallback → renders empty list | Graceful |
| Band value is unexpected | `default` case → gray pill | Cosmetic |
| User uploads enormous file | No size limit — may cause browser/backend OOM | Silent resource issue |

---

## 8. Glossary

**Agent** — In this context, a self-contained Python function (or set of functions) that processes one type of input (photos, audio, or CSV) and returns structured data. Not a truly autonomous AI agent — more of a "smart processor."

**Agentic Pipeline** — A series of processing steps where multiple agents run (some concurrently, some sequentially) and their outputs are aggregated into a final result. The "pipeline" is the `/report` endpoint.

**Band** — A qualitative rating on a three-level scale: Low, Moderate, Strong. Used for revenue consistency, inventory observation, and digital activity. Analogous to a traffic-light system.

**ChromaDB** — An open-source, embeddable vector database. It stores text chunks as vectors (numerical representations) and can find similar chunks by cosine similarity. Runs locally as files on disk — no separate server needed.

**Chunk** — A fixed-size segment of text (800 characters) extracted from a PDF. PDFs are too large to send to an LLM directly, so they're split into chunks, embedded, and stored. At query time, only the most relevant chunks are retrieved.

**Cold Start** — The delay when a serverless/deployed application starts up for the first time or after idle. Models (Whisper, ONNX) need to be downloaded and loaded, causing several seconds of latency on the first request.

**Concurrent Execution** — Running multiple tasks seemingly at the same time. Python's `asyncio.gather()` with `asyncio.to_thread()` allows the vision, voice, and transaction agents to run in parallel threads while the main event loop stays responsive.

**Cosine Similarity** — A measure of how similar two vectors are (range -1 to 1). Used by ChromaDB to find text chunks whose embedding vector is closest to the query's embedding vector. 1.0 = identical direction, 0 = unrelated.

**Embedding** — The process of converting text into a fixed-size vector (list of numbers) that captures semantic meaning. `all-MiniLM-L6-v2` converts any text into a 384-dimensional vector. Similar texts produce similar vectors.

**Ephemeral Storage** — Temporary disk space that is wiped when the server restarts. Render free tier and many serverless platforms use ephemeral storage, meaning ChromaDB data and downloaded ML models disappear on each deploy or cold start.

**Graceful Degradation** — The system continues to function (with reduced quality) when a component fails. For example, if no photos are uploaded, the report is still generated using voice and transaction data, with a "missing photos" note.

**Markdown Fence** — Triple backticks (`` ```json ... ``` ``) used to wrap code blocks in Markdown. LLMs often wrap JSON output in these. The synthesis and voice agents strip them before parsing.

**ONNX (Open Neural Network Exchange)** — A format for representing ML models. ChromaDB bundles an ONNX version of `all-MiniLM-L6-v2` that runs via ONNX Runtime, avoiding the need for PyTorch or TensorFlow. This is what makes the embedding step lightweight (~79MB).

**OpenRouter** — A unified API gateway that provides access to many LLMs through a single OpenAI-compatible endpoint. Used here to call `google/gemini-2.5-flash` (for vision) and `ibm-granite/granite-4.1-8b` (for text synthesis) through the same `openai` Python library.

**RAG (Retrieval-Augmented Generation)** — A technique where an LLM query is augmented with relevant documents retrieved from a knowledge base. In this project: the user's question about a business is augmented with SIDBI/RBI scheme documents from ChromaDB before being sent to the synthesis LLM, so the report references actual policy.

**Singleton** — A design pattern where a class/object is instantiated only once. The Whisper model in `voice_agent.py` uses this pattern — the model is loaded on the first request and reused for all subsequent requests.

**`asyncio.to_thread()`** — Runs a synchronous (blocking) function in a separate thread, allowing the async event loop to continue serving other requests while the function executes. Critical for running Whisper (CPU-intensive) and OpenRouter API calls (network I/O) without blocking the server.

**Vector Database** — A database that stores and queries vectors (embeddings). Unlike traditional databases that search by exact keywords, vector databases find items by semantic similarity. ChromaDB is the vector database used here.

**Whisper** — OpenAI's open-source speech recognition model. `faster-whisper` is a reimplementation using CTranslate2 that runs ~4x faster than the original while using less memory. The `base` variant is the second-smallest size (~140MB on disk).
