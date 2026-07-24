# Theligai — Business Readiness Report: Final Project Report

> Generated from actual codebase at commit `e95c104`. Every statement below is verified against the real files.

---

## 1. PROJECT OVERVIEW

| Field | Value |
|---|---|
| **Name** | Theligai |
| **One-line description** | AI-assisted MSME field assessment tool that generates a business readiness report from shop photos, a voice note, and a transaction CSV. |
| **Target user** | Microfinance field officers conducting vendor visits for SIDBI-style lending assessment. |
| **Core problem solved** | Manual assessment of MSME loan applications is slow and subjective. Theligai ingests raw field evidence (photos, voice recording, bank statement CSV), runs a multi-agent AI pipeline with RAG context from SIDBI/RBI scheme documents, and produces a structured, cachable readiness report with cross-source discrepancy flags. |

---

## 2. FULL ARCHITECTURE

### 2.1 Data Flow (end-to-end)

```
User Browser (Next.js)
    │
    │ 1. User selects files (photos, audio, CSV)
    │
    ├──► [Progressive path, if photos selected]
    │     ├── POST /agents/vision  (immediately, in background)
    │     └── POST /agents/voice   (immediately, in background)
    │
    │ 2. User clicks "Generate Report"
    │
    ├──► [If precomputed results exist]
    │     └── POST /report/synthesize
    │           with Form fields: vision_result (JSON str), voice_result (JSON str),
    │                              transactions (File, optional)
    │
    └──► [Else / fallback]
          └── POST /report
                with files: photos (multiple), audio (single), transactions (single)
```

### 2.2 Backend Processing Flow (both endpoints converge here)

```
                    ┌─────────────────────────────┐
                    │     POST /report/synthesize  │ (vision/voice pre-computed as JSON)
                    │  OR                          │
                    │     POST /report             │ (raw files, runs agents)
                    └──────────┬──────────────────┘
                               │
              ┌────────────────┼──────────────────┐
              ▼                ▼                   ▼
     vision_agent.py    voice_agent.py     transaction_agent.py
     analyze_photos()   process_voice()    analyze_transactions()
     (synchronous)      (synchronous)      (synchronous)
       runs in             runs in            runs in
     asyncio.to_thread   asyncio.to_thread  asyncio.to_thread
              │                │                   │
              │   (Concurrent via asyncio.gather in /report)
              │   (Sequential in /report/synthesize — only transactions is new)
              └────────┬───────┴───────────────────┘
                       ▼
                retrieve() from RAG
                (chromadb, synchronous)
                       │
                       ▼
                synthesis_agent.py
                synthesize_report() (LLM call, synchronous)
                       │
                       ▼
                _finalize_report() helper
                - injects financial fields from transaction_result
                - builds sources_cited from RAG context
                - generates UUID report_id
                - saves to backend/report_cache/{report_id}.json
                - returns final JSON response
```

### 2.3 Concurrency Model

| Step | In `/report` | In `/report/synthesize` |
|---|---|---|
| Vision agent | Concurrent (asyncio.gather with voice, transactions) | **Skipped** — result is already pre-computed |
| Voice agent | Concurrent (asyncio.gather with vision, transactions) | **Skipped** — result is already pre-computed |
| Transaction agent | Concurrent (asyncio.gather with vision, voice) | Sequential (only one agent call) |
| RAG retrieval | Sequential (after all agents complete) | Sequential (after transaction agent) |
| Synthesis | Sequential (after RAG) | Sequential (after RAG) |
| Finalize | Sequential | Sequential |

Each agent call runs via `asyncio.to_thread()` so the synchronous Python code (OpenAI calls, Whisper transcription, pandas) does not block the async event loop.

### 2.4 File Involvement per Step

| Step | File | Function(s) |
|---|---|---|
| Route registration | `backend/app/main.py` | `report()`, `report_synthesize()`, `_finalize_report()` |
| Vision analysis | `backend/app/agents/vision_agent.py` | `analyze_photos()`, `_describe_image()` |
| Voice transcription + extraction | `backend/app/agents/voice_agent.py` | `process_voice()`, `_get_whisper()` |
| Transaction CSV parsing | `backend/app/agents/transaction_agent.py` | `analyze_transactions()`, `_normalise_columns()`, `_find_amount_col()` |
| Report synthesis (LLM) | `backend/app/agents/synthesis_agent.py` | `synthesize_report()`, `_strip_fences()` |
| RAG retrieval | `backend/app/rag/retrieve.py` | `retrieve()` |
| RAG ingestion | `backend/app/rag/ingest.py` | `ingest()` |
| Agent helper (temp files, threading) | `backend/app/main.py` | `_run_agent()` |
| Frontend page | `frontend/app/page.tsx` | `Page()`, `handlePhotos()`, `handleAudio()`, `handleSubmit()`, `fetchReports()`, `viewReport()`, `reset()` |

---

## 3. COMPLETE FILE STRUCTURE

```
HackVerse/
├── .gitignore
├── ARCHITECTURE_DEEP_DIVE.md
├── AUDIT_REPORT.md
├── PROJECT_SUMMARY.md
├── README.md
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app — all routes
│   │   ├── agents/
│   │   │   ├── synthesis_agent.py     # LLM report synthesis
│   │   │   ├── transaction_agent.py   # CSV → financial metrics
│   │   │   ├── vision_agent.py        # Image → descriptions + summary
│   │   │   └── voice_agent.py         # Audio → transcript → JSON extraction
│   │   └── rag/
│   │       ├── __init__.py
│   │       ├── ingest.py              # PDF → ChromaDB ingestion
│   │       └── retrieve.py            # Query → RAG context
│   ├── data/
│   │   └── sidbi_docs/
│   │       ├── rbi_msme_master_direction.pdf
│   │       ├── sidbi_direct_finance.pdf
│   │       └── sidbi_mudra_shishu_faq.pdf
│   └── report_cache/                  # gitignored — JSON report files
├── frontend/
│   ├── .gitignore
│   ├── README.md
│   ├── eslint.config.mjs
│   ├── next.config.ts
│   ├── package-lock.json
│   ├── package.json
│   ├── postcss.config.mjs
│   ├── tsconfig.json
│   ├── app/
│   │   ├── favicon.ico
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx                   # Single-page app (upload + report + history)
│   └── public/
│       ├── file.svg
│       ├── globe.svg
│       ├── next.svg
│       ├── vercel.svg
│       └── window.svg
└── test_media/
    ├── Record_1.wav
    ├── contradiction_voice.wav
    ├── contradiction_voice2.wav
    ├── fake.jpg
    ├── fake_voice_note.txt
    ├── photo1.jpg
    ├── photo2.jpg
    ├── test_1_pic.avif
    ├── trans_1.csv
    ├── transactions.csv
    └── voicenote.wav
```

---

## 4. TECH STACK

| Layer | Technology | Exact version / model | Notes |
|---|---|---|---|
| **Backend framework** | FastAPI | (pip: latest) | Python 3.11+ |
| **Backend ASGI server** | Uvicorn | (pip: latest) | |
| **Vision LLM** | Google Gemini 2.5 Flash via OpenRouter | `google/gemini-2.5-flash` | Called via `openai` library with custom base_url |
| **Text LLM** | IBM Granite 4.1 8B via OpenRouter | `ibm-granite/granite-4.1-8b` | Used for voice extraction + synthesis |
| **LLM provider** | OpenRouter | `https://openrouter.ai/api/v1` | One API key for both models |
| **Speech-to-text** | faster-whisper | `tiny` model, `int8` compute, CPU | Lazy-loaded singleton |
| **Vector DB** | ChromaDB | `chromadb` (pip) | Persistent, on-disk at `backend/chroma_db/` |
| **Embeddings** | ONNX-based (ChromaDB default) | n/a | No external embedding API used |
| **PDF parsing** | PyPDF / langchain | `pypdf` + `langchain_community` | |
| **Text splitting** | RecursiveCharacterTextSplitter | chunk_size=800, overlap=100 | |
| **Data processing** | pandas, numpy | Standard | |
| **Frontend framework** | Next.js 16.2.10 | React 19.2.4 | TypeScript, strict mode |
| **CSS** | Tailwind CSS v4 | `@tailwindcss/postcss` | |
| **Fonts** | Geist (sans), Geist Mono | via `next/font/google` | |
| **Hosting (frontend)** | Vercel | `next build` → `next start` | |
| **Hosting (backend)** | Render (free tier) | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | |

**Authentication**: None. The app has no login, no session management, no API key restrictions on the backend endpoints.

---

## 5. ALL API ENDPOINTS

### 5.1 `GET /health`
- **Purpose**: Health check
- **Response**: `{"status": "ok"}`

### 5.2 `GET /reports`
- **Purpose**: List all cached reports, sorted by most recent first
- **Response**: `Array<{ report_id: string, business_type: string | null, assessment_band: string, generated_at: string }>`
- **Error handling**: Silently skips corrupt JSON files

### 5.3 `GET /reports/{report_id}`
- **Purpose**: Retrieve a single cached report by ID
- **Response**: Full report JSON object
- **404**: `{"error": "report not found"}`

### 5.4 `POST /rag/query`
- **Purpose**: Direct RAG query (debugging / inspection)
- **Request body**: `{"query": "string"}`
- **Response**: `{"query": "...", "results": Array<{content: string, source: string}>}`

### 5.5 `POST /agents/vision`
- **Purpose**: Standalone vision analysis (called by frontend progressive processing)
- **Request**: `files: UploadFile[]` (multipart, field name `files`)
- **Response**: JSON from `analyze_photos()` → `{"per_image": [...], "summary": "..."}` or `{"error": "...", "detail": "..."}`

### 5.6 `POST /agents/voice`
- **Purpose**: Standalone voice processing (called by frontend progressive processing)
- **Request**: `file: UploadFile` (multipart, field name `file`)
- **Response**: JSON from `process_voice()` → `{"transcript": "...", "extracted": {...}, "label": "officer observation, unverified"}`

### 5.7 `POST /report/synthesize`
- **Purpose**: Generate report from pre-computed vision + voice results (progressive path)
- **Request**: `multipart/form-data`
  - `vision_result`: `str` (JSON string, form field, optional) — output from `/agents/vision`
  - `voice_result`: `str` (JSON string, form field, optional) — output from `/agents/voice`
  - `transactions`: `File` (file upload, optional)
- **Response**: Full report JSON (same shape as `/report`)
- **Introduced in**: commit `e95c104` (progressive processing feature)

### 5.8 `POST /report`
- **Purpose**: Generate report from raw uploaded files (fallback / non-progressive path)
- **Request**: `multipart/form-data`
  - `photos`: `UploadFile[]` (multiple, field name `photos`, optional)
  - `audio`: `UploadFile` (single, field name `audio`, optional)
  - `transactions`: `UploadFile` (single, field name `transactions`, optional)
- **Response** (both endpoints):

```jsonc
{
  "report_id": "uuid-string",
  "business_type": "string or null",
  "revenue_consistency_band": "Low" | "Moderate" | "Strong",
  "inventory_observation_band": "Low" | "Moderate" | "Strong",
  "digital_activity_band": "Low" | "Moderate" | "Strong",
  "relevant_scheme_note": "one-sentence string",
  "assessment_band": "Further assessment required" | "Suitable for micro-loan assessment" | "Suitable for higher assessment range",
  "evidence_summary": ["string", ...],
  "missing_inputs": ["photos"?, "voice"?, "transactions"?],
  "input_errors": ["string", ...],
  "discrepancy_flags": ["string", ...],
  "source_agreement": {
    "photo_voice": "agree" | "conflict" | "insufficient_data",
    "photo_transactions": "agree" | "conflict" | "insufficient_data",
    "voice_transactions": "agree" | "conflict" | "insufficient_data"
  },
  "sources_cited": ["filename.pdf", ...],
  // Only present if transactions were provided and parseable:
  "total_inflow": number,
  "total_outflow": number,
  "transaction_count": number,
  "average_transaction": number,
  "volatility": "low" | "moderate" | "high",
  "trend": "increasing" | "decreasing" | "stable",
  "date_range_days": number | null,
  "earliest_date": "YYYY-MM-DD" | null,
  "latest_date": "YYYY-MM-DD" | null,
  // Internal diagnostics:
  "_timings": { "rag": number, "synthesis": number }
}
```

---

## 6. EACH AGENT IN DETAIL

### 6.1 `vision_agent.py` — `analyze_photos(image_paths: list[str]) -> dict`

**Signature**: `analyze_photos(image_paths: list[str]) -> dict`

**Process**:
1. For each image path, calls `_describe_image(path)` which:
   - Reads the file, base64-encodes it
   - Calls `google/gemini-2.5-flash` via OpenRouter with `max_tokens=300`
   - Prompt: *"Describe the visible inventory, shop condition, and activity level in this image factually. Do not judge quality or health, only describe what is visible."*
2. Combines all descriptions, calls the same model again with:
   - Prompt: *"Based on these checkpoint descriptions, state only which visible categories of inventory appear similar or different across images. Do not conclude anything about business health."*
3. Returns `{"per_image": [{"file": "...", "description": "..."}, ...], "summary": "..."}`

**Error paths**:
- If any `_describe_image` call throws → returns `{"error": "vision processing failed", "detail": str(e)}`
- If the summary call throws → same error shape

**Unused imports / missing imports**: `sys` is used on line 10 (`file=sys.stderr`) but **`import sys` is missing** at the module level. If `OPENROUTER_API_KEY` is unset, this will raise `NameError` before the fallback assignment on line 11 can execute.

### 6.2 `voice_agent.py` — `process_voice(audio_path: str) -> dict`

**Signature**: `process_voice(audio_path: str) -> dict`

**Process**:
1. Lazy-loads `faster-whisper` model (`tiny`, CPU, `int8`) — singleton pattern via `_get_whisper()`
2. Transcribes audio file → concatenated transcript string
3. Calls `ibm-granite/granite-4.1-8b` via OpenRouter with `max_tokens=300`
   - Prompt: *"Extract ONLY the following if mentioned: business type, products/services, years operating, location. Do not infer tone, confidence, honesty, or emotional state. Return strict JSON with keys business_type, products, years_operating, location. Omit a key entirely if not mentioned."*
4. Strips markdown fences from the response, attempts `json.loads()`
5. Returns `{"transcript": "...", "extracted": {...}, "label": "officer observation, unverified"}`

**Error paths**:
- If JSON parsing fails → `extracted` falls back to `{"raw_response": raw_text}` (graceful degradation)
- If OpenRouter or Whisper throws → exception propagates to `_run_agent()` which does NOT catch it; the route handler will return a 500 error

**Note**: No `try/except` around the `model.transcribe()` or `or_client.chat.completions.create()` calls. Any network or model error will bubble up to FastAPI's default exception handler.

### 6.3 `transaction_agent.py` — `analyze_transactions(csv_path: str) -> dict`

**Signature**: `analyze_transactions(csv_path: str) -> dict`

**Process**:
1. Validates file exists and `pd.read_csv()` succeeds → otherwise returns `{"error": "transaction data unavailable"}`
2. Column normalization (`_normalise_columns`): maps case-insensitive variants of date/type/amount/debit/credit column names to canonical names
3. **Column structure detection** (three paths):
   - **Separate debit/credit columns**: un-pivots into per-row type+amount
   - **Single amount column with mixed signs**: infers debit/credit from sign
   - **Single amount column, all same sign**: treats all as inflow (adds note to `assumptions[]`)
   - If no amount-like column found → returns error
4. Computes: `total_inflow`, `total_outflow`, `transaction_count`, `average_transaction`
5. Date range: `earliest_date`, `latest_date`, `date_range_days`
6. Volatility: CV of daily net amounts → `low` (<0.5), `moderate` (0.5-1.0), `high` (>1.0)
7. Trend: linear slope of monthly net totals → `increasing` / `decreasing` / `stable`

**Error paths**:
- Missing file, unreadable CSV, empty data, missing date column, missing amount columns → `{"error": "transaction data unavailable"}`
- Date parsing failures → date range fields set to `None`
- Volatility/trend computation failures → defaults to 0.0 / "stable"

### 6.4 `synthesis_agent.py` — `synthesize_report(vision_result, voice_result, transaction_result, rag_context) -> dict`

**Signature**: `synthesize_report(vision_result: dict | None, voice_result: dict | None, transaction_result: dict | None, rag_context: list) -> dict`

**Model**: `ibm-granite/granite-4.1-8b` via OpenRouter, `max_tokens=600`

**System prompt** (151 lines in `SYSTEM_PROMPT` constant):
- Instructs the model to act as a financial assessment assistant for MSME lending
- Rules: no invented scores, base bands only on evidence, output valid JSON only, actively cross-check sources for contradictions
- Specific cross-checks enumerated: inventory vs sales volume, business tenure vs transaction date span, revenue vs digital activity
- `source_agreement` instructions: assess each pair independently, use "insufficient_data" if a source is missing

**User prompt** constructed from:
- Evidence blocks: `[photos: {...}]`, `[voice: {...}]`, `[transactions: {...}]` (or `[photos: missing]` etc.)
- Transaction date info appended as `[Transaction records span X days...]` when available
- RAG context block (concatenated `content` fields)

**Expected output keys** (enforced by prompt + post-processing):
- `business_type`: string or null
- `revenue_consistency_band`: "Low" | "Moderate" | "Strong"
- `inventory_observation_band`: "Low" | "Moderate" | "Strong"
- `digital_activity_band`: "Low" | "Moderate" | "Strong"
- `relevant_scheme_note`: string (one sentence)
- `assessment_band`: one of three allowed values
- `evidence_summary`: list of strings
- `missing_inputs`: list of strings
- `discrepancy_flags`: list of strings
- `source_agreement`: dict with keys photo_voice, photo_transactions, voice_transactions

**Post-processing validation**:
- Missing `discrepancy_flags` → defaults to `[]`
- Invalid `source_agreement` keys → defaults to all "insufficient_data"
- Invalid band values → defaults to "Further assessment required"
- Invalid assessment_band → defaults to "Further assessment required"
- Markdown fences stripped from LLM output before JSON parsing

**Error paths**:
- If the LLM call fails or JSON parsing fails → `{"error": "synthesis failed", "detail": str(e), "raw_response": raw}`

---

## 7. THE PROGRESSIVE PROCESSING FEATURE

### 7.1 What it does

Instead of waiting for all three agents (vision, voice, transactions) to run sequentially/concurrently at submit time, the frontend fires the vision and voice agent calls **immediately** when the user selects the files — while they're still filling out the rest of the form. By the time they click "Generate Report", those results are often already available, so the submit request only needs to run the fast transaction parser + RAG + synthesis.

### 7.2 End-to-end flow

1. **User selects photos** → `handlePhotos()` fires `POST /agents/vision` with the files in background
2. **User selects audio** → `handleAudio()` fires `POST /agents/voice` in background
3. **User clicks "Generate Report"** → `handleSubmit()` runs:
   - **Step A**: Check `precomputedVisionLoadingRef.current` and `precomputedVoiceLoadingRef.current`. If still loading, enter a polling loop (200ms intervals) that reads the refs (always live) until they clear.
   - **Step B**: Read `precomputedVisionRef.current` and `precomputedVoiceRef.current` (refs, not state).
   - **Step C**: If either ref has a non-null result → send to `POST /report/synthesize` with `vision_result` and/or `voice_result` as JSON-string form fields, plus the transactions CSV file.
   - **Step D**: If neither ref has a result → send raw files to the legacy `POST /report` endpoint.

### 7.3 Bug fix 1: `Form()` annotation (backend)

The `/report/synthesize` endpoint originally declared parameters as:
```python
async def report_synthesize(
    vision_result: str = None,
    voice_result: str = None,
    ...
):
```

In FastAPI, when at least one `File()` parameter exists in a route, all non-file parameters **must** be annotated with `Form()` to be read from the multipart form body. Without `Form()`, FastAPI treats them as query parameters, which always resolve to `None`. The fixed signature:
```python
async def report_synthesize(
    vision_result: str = Form(None),
    voice_result: str = Form(None),
    ...
):
```

### 7.4 Bug fix 2: Stale closure with `useRef` (frontend)

The original `handleSubmit()` used a polling loop based on booleans captured in the `useCallback` closure:
```typescript
while (precomputedVisionLoading) { /* never exits — stale closure */ }
if (precomputedVision) { /* also stale — always null */ }
```

React state variables captured in a closure do not update when the state changes. The fix adds `useRef` mirrors for both loading flags and result values:
- `precomputedVisionLoadingRef.current` / `precomputedVoiceLoadingRef.current` — always live, polled in the while loop
- `precomputedVisionRef.current` / `precomputedVoiceRef.current` — always live, read after the loop exits

### 7.5 UI indicators

- **During processing**: pulsing indigo dot + "Processing photos..." / "Processing voice note..."
- **On completion**: static green dot + "Ready"
- **During submit wait**: "Finishing analysis..." (waiting for background agents) → "Generating report..." (calling synthesis endpoint)
- **CSV section**: static green dot + "Ready" when file selected (no pre-processing needed)

---

## 8. CROSS-VERIFICATION / DISCREPANCY DETECTION

### 8.1 Prompt logic (in `synthesis_agent.py`)

The system prompt instructs the LLM to:
1. Cross-check inventory levels in photos vs. sales volume in transactions
2. Compare business tenure from voice note vs. actual transaction date span
3. Assess revenue level vs. digital activity plausibility
4. Flag any other factual inconsistency between what was said, shown, and recorded
5. For each contradiction, phrase as a neutral observation for the officer

The source_agreement section instructs the model to evaluate each pair independently with `"agree"`, `"conflict"`, or `"insufficient_data"`.

### 8.2 Output fields

**`discrepancy_flags: string[]`**:
- Each element is a human-readable sentence describing one cross-source contradiction
- Returned as empty list `[]` if no contradictions found or insufficient evidence
- Example: *"Voice note states business has been operating for 3 years, but transaction records span only 6 months (180 days)."*

**`source_agreement: { photo_voice, photo_transactions, voice_transactions }`**:
- Each key is one of `"agree"`, `"conflict"`, or `"insufficient_data"`
- Used to render the visual cross-verification matrix on the report screen (colored connectors + status pills)

### 8.3 Frontend rendering

The report screen renders a 3-node diagram:
- Top row: Photo ↔ Voice (horizontal connector with status pill)
- Bottom: Transactions (centered)
- Vertical connectors: Photo↔Transactions, Voice↔Transactions
- Colors: green for "agree", amber for "conflict", grey for "insufficient_data"
- Discrepancy flags render in an amber "Needs Officer Review" card below the matrix

---

## 9. FRONTEND STATE MACHINE

### 9.1 Screens

| Screen | Condition | Renders |
|---|---|---|
| `"upload"` | Default, `screen === "upload"` | File upload cards + submit button |
| `"report"` | `screen === "report" && report !== null` | Full report view with all sections |
| `"history"` | `screen === "history"` | Past reports list |

### 9.2 State variables

| Variable | Type | Purpose |
|---|---|---|
| `screen` | `"upload" \| "report" \| "history"` | Current view |
| `photos` | `File[]` | Selected photo files |
| `audio` | `File \| null` | Selected audio file |
| `csv` | `File \| null` | Selected CSV file |
| `precomputedVision` | `any \| null` | Result from background vision agent call (for UI re-render) |
| `precomputedVoice` | `any \| null` | Result from background voice agent call (for UI re-render) |
| `precomputedVisionLoading` | `boolean` | Whether vision agent is still processing (UI indicator) |
| `precomputedVoiceLoading` | `boolean` | Whether voice agent is still processing (UI indicator) |
| `loading` | `boolean` | Whether report generation is in progress |
| `loadingPhase` | `"finishing" \| "generating"` | Sub-state during loading |
| `report` | `Report \| null` | Current report data |
| `error` | `string \| null` | Error message |
| `reports` | `ReportSummary[]` | History list |
| `historyLoading` | `boolean` | Whether history is loading |

### 9.3 Refs (live values, not captured in closures)

| Ref | Purpose |
|---|---|
| `audioRef` | Reference to audio file input element |
| `csvRef` | Reference to CSV file input element |
| `precomputedVisionLoadingRef` | Live loading flag for vision (polled by handleSubmit) |
| `precomputedVoiceLoadingRef` | Live loading flag for voice (polled by handleSubmit) |
| `precomputedVisionRef` | Live vision result (read after wait-loop) |
| `precomputedVoiceRef` | Live voice result (read after wait-loop) |

### 9.4 Conditional renders

- Button disabled when `!canSubmit || loading`
- Loading spinner shown only when `loading` is true
- Error card shown only when `error` is non-null
- Processing indicator only when `precomputedVisionLoading` / `precomputedVoiceLoading`
- Ready indicator only when loading complete AND result exists AND file still selected
- Financial evidence card only when `report.transaction_count !== undefined`
- Cross-verification matrix only when `report.source_agreement` exists
- Discrepancy flags card only when `report.discrepancy_flags.length > 0`
- Missing inputs note only when `report.missing_inputs.length > 0`
- Sources cited only when `report.sources_cited.length > 0`

---

## 10. DEPLOYMENT

### 10.1 Backend (Render)

**Build command**:
```bash
pip install -r backend/requirements.txt
```

**Start command**:
```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**First-time setup** (run once after deploy):
```bash
python -m app.rag.ingest
```
This ingests the 3 PDFs in `backend/data/sidbi_docs/` into a persistent ChromaDB at `backend/chroma_db/`.

**Environment variables**:
```
OPENROUTER_API_KEY=sk-or-v1-...
```

**Known infrastructure constraints on Render free tier**:
- **Memory**: 512 MB RAM. `faster-whisper` tiny model + ChromaDB ONNX embeddings fit, but barely. The Whisper model is lazy-loaded to avoid memory at import time.
- **Cold start**: First request after idle spins up the Whisper model + loads ChromaDB — can take 10-20 seconds. Subsequent requests are faster.
- **Disk**: Ephemeral. The `chroma_db/` directory persists across deploys only if using Render's disk feature or a separate volume. On free tier, data is lost on restart. The `report_cache/` directory is also ephemeral on free tier.
- **No GPU**: All ML runs on CPU. `faster-whisper` tiny + `int8` is usable but slow (~5-15s for a 30s audio clip).

### 10.2 Frontend (Vercel)

**Build command**:
```bash
cd frontend && npm install && npm run build
```

**Start command**: Auto-detected by Vercel (`next start`)

**Environment variables**:
```
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com/report
```

**Note**: During development, `NEXT_PUBLIC_API_URL` defaults to `http://127.0.0.1:8001/report` if not set (hardcoded in `page.tsx` line 5). The `/report` suffix is stripped via `API_BASE` to derive agent endpoint URLs.

---

## 11. SECURITY & AUDIT STATUS

| Check | Result |
|---|---|
| **Secrets in git history** | CLEAN — `backend/.env` has never been tracked. The only `.env` file in history is `.env.example` with placeholder `sk-or-v1-your-key-here`. |
| **API key regex scan** | CLEAN — matches are only in doc files referencing the placeholder pattern. |
| **`sys.exit()` in backend/app/** | 0 occurrences |
| **TODO/FIXME/XXX/console.log** | 0 occurrences in source code |
| **Debug print() statements** | 1 intentional timing log in `_run_agent()` — acceptable. |
| **Stale test artifacts** | REMOVED — `temp_vision.json` and `temp_voice.json` were deleted in the final commit. |
| **CORS configuration** | Only `http://localhost:3000` and `https://hack-verse-psi.vercel.app` are allowed. |
| **Dependency duplicates** | None — 14 unique packages in `requirements.txt`. |
| **`report_cache/` gitignore** | Properly gitignored and not tracked. |
| **Route duplication** | CLEAN — 8 routes, each defined exactly once. |
| **Missing import** | ⚠️ **`backend/app/agents/vision_agent.py`**: `sys` is referenced on line 10 (`file=sys.stderr`) but not imported. This will cause a `NameError` at runtime if `OPENROUTER_API_KEY` is not set. |

---

## 12. KNOWN LIMITATIONS

1. **No authentication / multi-tenancy** — The app has no login system. The history view shows *all* cached reports. The README notes "Production version would restrict this to the logged-in officer's own history."
2. **Ephemeral storage on Render free tier** — ChromaDB vector store and `report_cache/` are lost on every restart. A production deploy would need a persistent disk or external DB.
3. **No transaction pre-processing on progressive path** — The progressive feature pre-computes vision and voice, but transactions are still parsed at submit time. This is by design (CSV parsing is fast) but means the progressive path doesn't fully eliminate the wait.
4. **Single CSV format assumption** — The transaction agent handles several column layouts but has hardcoded heuristics for specific column name variants. Unusual bank statement formats may fail.
5. **No streaming** — The entire report is generated server-side before returning. For long-running syntheses, the user sees only a spinner with no partial output.
6. **Voice note language** — `faster-whisper` tiny model is English-only by default. Non-English voice notes will produce garbled transcripts.
7. **No file size limits** — The backend accepts any file size. Large photos or long audio recordings could cause memory issues on the 512 MB Render free tier.
8. **OpenRouter dependency** — If OpenRouter is down or rate-limited, the entire pipeline fails. There is no fallback LLM provider or retry logic.
9. **Prompt brittleness** — The synthesis agent relies on the LLM following a detailed JSON schema prompt. If the model drifts (new version, different provider), the JSON output may require re-prompting.

---

## 13. GAPS OR RISKS IDENTIFIED

These are **new findings** not discussed in prior conversations:

### 13.1 Missing `import sys` in `vision_agent.py` (CONFIRMED BUG)

File: `backend/app/agents/vision_agent.py`, line 10:
```python
print("ERROR: OPENROUTER_API_KEY environment variable is not set.", file=sys.stderr)
```

`sys` is never imported. If the environment variable is missing, this line will throw `NameError: name 'sys' is not defined` *before* the fallback `api_key = ""` on line 11 executes. The app will crash at import time with a misleading error.

**Risk**: Low in production (env var is set), but would cause a confusing failure in local dev if someone forgets to configure `.env`.

### 13.2 Unhandled exceptions in `voice_agent.py` (FRAGILE)

`process_voice()` wraps the JSON parsing in try/except but does **not** wrap `model.transcribe()` or `or_client.chat.completions.create()`. If Whisper transcription fails (corrupt audio file, out of memory) or the OpenRouter call times out, the exception propagates uncaught to FastAPI's default 500 handler, returning a generic `{"detail": "Internal Server Error"}` with no useful information for debugging.

**Risk**: Medium. A corrupt audio file from a field officer's phone could result in an opaque error rather than a graceful message.

### 13.3 `handleSubmit` dependency array includes unused state variables

At `page.tsx` line 196:
```typescript
}, [photos, audio, csv, precomputedVision, precomputedVoice]);
```

`precomputedVision` and `precomputedVoice` are state variables that are **no longer read** inside `handleSubmit` (the code reads from refs instead). They trigger unnecessary re-creation of the callback on every state change. This is not a bug but is wasteful — and it means the closure's `precomputedVision` / `precomputedVoice` references are dead code in the dependency declaration.

**Risk**: Very low. Harmless, just slightly inefficient.

### 13.4 Hardcoded `API_BASE` URL derivation is fragile

At `page.tsx` line 6:
```typescript
const API_BASE = API.replace(/\/report$/, "");
```

This assumes `NEXT_PUBLIC_API_URL` always ends with `/report`. If someone configures a URL that doesn't match this pattern (e.g., `https://api.example.com/`), `API_BASE` will be identical to `API`, and agent endpoint URLs will be wrong (e.g., `https://api.example.com/agents/vision` instead of `https://api.example.com/report/agents/vision`).

**Risk**: Low, given the intended deployment model, but fragile.

### 13.5 No `Content-Type` validation on file upload endpoints

The `/agents/vision` and `/agents/voice` endpoints accept any file type without MIME type checking. A user could upload a non-image to the vision endpoint or a non-audio file to the voice endpoint. The downstream agents will fail with opaque errors.

**Risk**: Low (field officers are the expected users, not adversarial).

### 13.6 `globals.css` CSS custom property ordering

At `frontend/app/globals.css`:
```css
:root {
  --background: #f8fafc;
  --foreground: #0f172a;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
}
```

The `@theme inline` block references `var(--background)` which is defined in the `:root` block. This works in practice because `@theme inline` is a Tailwind directive processed at build time, not runtime CSS. However, the pattern is unusual and could confuse future maintainers.

**Risk**: None functional, just stylistic.

### 13.7 Neither endpoint validates that at least one input was provided

`POST /report` and `POST /report/synthesize` accept all-`None` inputs. The pipeline would proceed with all three `_result` variables set to `None`, the synthesis agent would receive all-missing evidence, and the report would be generated with no data. The frontend disables the submit button when nothing is selected (`canSubmit`), but direct API calls bypass this check.

**Risk**: Low (only affects direct API callers, not the UI).
