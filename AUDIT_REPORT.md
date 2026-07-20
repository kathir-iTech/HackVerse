# Project Audit Report — HackVerse (SIDBI Business Readiness Report)

Generated: 2026-07-20

---

## 1. Directory Tree

```
HackVerse/
├── .gitignore                          # Root gitignore (Python, Node, ChromaDB, env, IDE, logs)
├── AUDIT_REPORT.md                     # ← this file
├── README.md                           # Basic setup docs
├── results.txt                         # ⚠️ TMP — stale audit output, should be deleted
├── temp_query.json                     # ⚠️ TMP — leftover test query, already committed in 83a7f37
├── uvicorn_log.txt                     # ⚠️ TMP — server log, excluded via .gitignore
│
├── backend/
│   ├── .env                            # Never committed (gitignored)
│   ├── .env.example                    # Placeholder values
│   ├── requirements.txt                # Python dependencies
│   ├── chroma_db/                      # Excluded via .gitignore (auto-created)
│   ├── app/
│   │   ├── __init__.py                 # Empty
│   │   ├── main.py                     # FastAPI app, 5 routes, CORS, concurrent agent dispatch
│   │   ├── agents/
│   │   │   ├── synthesis_agent.py      # Aggregates all agent outputs + RAG → LLM JSON report
│   │   │   ├── transaction_agent.py    # CSV parsing → volatility/trend metrics
│   │   │   ├── vision_agent.py         # OpenRouter vision (gemini-2.5-flash) per-image + summary
│   │   │   └── voice_agent.py          # Whisper base → OpenRouter extraction
│   │   └── rag/
│   │       ├── __init__.py             # Empty
│   │       ├── ingest.py               # PDF → chunk → ChromaDB (native chromadb client)
│   │       └── retrieve.py             # ChromaDB query → {content, source}[]
│   └── data/
│       └── sidbi_docs/
│           └── sidbi_direct_finance.pdf  # 21-page SIDBI direct finance PDF
│
├── frontend/
│   ├── .gitignore                      # Next.js default gitignore
│   ├── dev_log.txt                     # ⚠️ TMP — dev server log, excluded via root .gitignore
│   ├── README.md                       # Next.js default README
│   ├── next.config.ts                  # Next.js config
│   ├── package.json                    # Dependencies: next, react, react-dom, tailwindcss, typescript
│   ├── package-lock.json               # Lockfile
│   ├── postcss.config.mjs              # PostCSS config (Tailwind)
│   ├── tsconfig.json                   # TypeScript config
│   ├── eslint.config.mjs               # ESLint flat config
│   ├── node_modules/                   # Excluded via .gitignore
│   ├── .next/                          # Excluded via .gitignore
│   ├── app/
│   │   ├── favicon.ico                 # Next.js default
│   │   ├── globals.css                 # Tailwind directives
│   │   ├── layout.tsx                  # Root layout (Geist fonts, UTF-8)
│   │   └── page.tsx                    # Single-page SPA: upload form + report screen
│   └── public/
│       ├── file.svg, globe.svg, next.svg, vercel.svg, window.svg  # Next.js default assets
│
└── test_media/
    ├── photo1.jpg, photo2.jpg          # Test shop photos
    ├── transactions.csv                # Test transaction data
    └── voicenote.wav                   # Test voice note
```

**Leftover/stale files to clean up:**
- `results.txt` — stale audit output from a previous run
- `temp_query.json` — already committed (83a7f37), consider removing with `git rm`
- `uvicorn_log.txt` — `.gitignore`-excluded but physically present; harmless
- `frontend/dev_log.txt` — `.gitignore`-excluded but physically present; harmless

---

## 2. Security Check

### 2a. Git history scan (`git log --all -p -- backend/.env backend/.env.example`)

- **`backend/.env`**: never committed. No output from `git log --all -p`.
- **`backend/.env.example`**: committed once in the initial commit with placeholder values (`sk-or-v1-your-key-here`, `hf_your-token-here`). **No live secrets in history.** ✅

### 2b. Hardcoded API keys (grep for `sk-or-v1` / `hf_`)

```
No occurrences found in any .py, .ts, .tsx, or .json file.
```

✅ **No hardcoded secrets.**

### 2c. `.gitignore` coverage

| Pattern | Covered? |
|---------|----------|
| `.env` | ✅ `backend/.gitignore` + root `.gitignore` |
| `.env.local` | ✅ root `.gitignore` |
| `chroma_db/` | ✅ root `.gitignore` |
| `__pycache__/` | ✅ root `.gitignore` |
| `node_modules/` | ✅ root `.gitignore` + `frontend/.gitignore` |
| `.next/` | ✅ root `.gitignore` + `frontend/.gitignore` |
| `venv/` | ✅ root `.gitignore` |
| `*.log` / `dev_log.txt` / `uvicorn_log.txt` | ✅ root `.gitignore` |
| `results.txt` | ✅ root `.gitignore` |
| `next-env.d.ts` | ✅ `frontend/.gitignore` |

**No findings.** ✅

---

## 3. Dependency Check

### 3a. `backend/requirements.txt` (14 packages)

```
fastapi
uvicorn
langchain
langchain-community
langchain-openai
chromadb
pypdf
python-multipart
python-dotenv
requests
faster-whisper
openai
pandas
numpy
```

**Flagged:**
- `langchain` and `langchain-community` — still used by `ingest.py` for `PyPDFLoader` and `RecursiveCharacterTextSplitter`. Not removable unless rewritten to use `pypdf` + custom splitter. Minor weight concern but acceptable.
- `langchain-openai` — appears unused. The agents call OpenAI directly via `openai` package, not through langchain wrappers. **Candidate for removal.**
- `requests` — appears unused across the codebase. **Candidate for removal.**
- No duplicates. ✅
- No `torch` or `sentence-transformers` since the ONNX embedding swap.

### 3b. `frontend/package.json` dependencies

```json
"dependencies": {
  "next": "16.2.10",
  "react": "19.2.4",
  "react-dom": "19.2.4"
},
"devDependencies": {
  "@tailwindcss/postcss": "^4",
  "@types/node": "^20",
  "@types/react": "^19",
  "@types/react-dom": "^19",
  "eslint": "^9",
  "eslint-config-next": "16.2.10",
  "tailwindcss": "^4",
  "typescript": "^5"
}
```

Minimal and clean. Three runtime deps (next, react, react-dom). No stale packages. ✅

---

## 4. Code-Level Review — Backend

### 4a. `backend/app/main.py` (180 lines)

**What it does:** FastAPI app with 5 routes (`/health`, `/rag/query`, `/agents/vision`, `/agents/voice`, `/report`). The `/report` route is the main pipeline: dispatches vision/voice/transaction agents concurrently via `asyncio.gather`, runs RAG retrieval, feeds everything to `synthesize_report`, and returns the structured JSON.

**Issues:**
- **`_run_agent` hardcodes timer assignment in `finally`** — the `timings[label]` line runs even if `files_data is None` (returns early), but that's fine because the function returns `None` before the `try` block if `files_data is None`. ✅ actually correct.
- **Import order** — `load_dotenv()` is called before importing local modules that read env vars. This is deliberate and correct. ✅
- **`/_run_agent` indentation** — `timings[label]` is in the `finally` block and runs even after `return result`. This is correct Python behavior (finally runs before return), but the timing will include cleanup. Minor: the timer spans file write + agent execution + file cleanup, not just agent execution. Acceptable.
- **`/rag/query` route** — uses `retrieve(req.query, k=3)`. The hardcoded `k=3` is fine, could be configurable. Minor.

### 4b. `backend/app/agents/vision_agent.py` (69 lines)

**What it does:** Takes image paths, base64-encodes each, sends to OpenRouter `google/gemini-2.5-flash` for description, then summarizes across images with a second call.

**Issues:**
- **`sys.exit(1)` on OpenRouter error** — kills the entire server process. Should raise an exception or return `{"error": "..."}`. ⚠️ **Medium severity.** If the vision agent fails on a single request, the whole uvicorn process dies. Replace with `raise` or return error dict.
- **`VISION_MODEL` and `TEXT_MODEL` hardcoded** — both set to `"google/gemini-2.5-flash"`. Not configurable without editing code. Low severity — could be env vars.
- **`DESCRIBE_PROMPT` / `SUMMARY_PROMPT_PREFIX` hardcoded** — fine for now, no sensitive data. ✅
- No unused HF code lingering. The migration from HF to OpenRouter is complete. ✅

### 4c. `backend/app/agents/voice_agent.py` (54 lines)

**What it does:** Loads Whisper `base` model (singleton), transcribes audio, sends transcript to OpenRouter `ibm-granite/granite-4.1-8b` for structured JSON extraction.

**Issues:**
- **`_get_whisper()` global singleton** — fine, avoids reloading the model on each request. ✅
- **`OPENROUTER_API_KEY` uses `os.getenv`** while other agents use `os.environ.get`. Inconsistent but functionally identical. Low severity.
- **No timeout on Whisper** — large audio files could block the worker thread indefinitely. Low-medium severity.
- **Markdown fence stripping** — present and correct. ✅

### 4d. `backend/app/agents/transaction_agent.py` (187 lines)

**What it does:** Parses CSV with flexible column name matching (date/type/amount variants, separate debit/credit columns), computes total inflow/outflow, transaction count, average, volatility (coefficient of variation of daily net), and month-over-month trend (linear slope).

**Issues:**
- **All amounts treated as `amount_usd`** — the field name `amount_usd` is in the variant set but there's no currency conversion or denomination tracking. If CSV uses INR (likely for an Indian lender), the amounts display without currency label. Low severity — should note currency assumption in output.
- **`assumptions` field** — only set when no direction indicator is found and all transactions are treated as inflow. Should also note when separate debit/credit columns are collapsed. Low.
- **`np.where` used with `pd.notna`** (line debit/credit logic) — `d > 0` and `c > 0` checks correctly skip NaN (NaN > 0 is False). ✅
- **No CSV file size limit** — large CSVs could cause OOM. Low-medium severity for a field-officer tool.

### 4e. `backend/app/agents/synthesis_agent.py` (101 lines)

**What it does:** Aggregates results from vision/voice/transaction agents + RAG context, sends to OpenRouter `ibm-granite/granite-4.1-8b` with a strict system prompt, parses JSON response.

**Issues:**
- **`sys.exit(1)` if `OPENROUTER_API_KEY` missing at module level** — kills the server on import. This is intentional (fail-fast on misconfiguration). ✅ for production, but could be more graceful.
- **`raw` variable referenced in except block via `"raw" in dir()`** — fragile. If `completion` fails before `raw` is assigned, `dir()` won't contain `"raw"`. The `raw_response` key will be `None`. Low severity, but a cleaner approach: initialize `raw = None` before the `try`.
- **No validation of LLM output shape** — if the LLM returns a JSON that omits required keys or adds extra keys, the frontend will get unexpected fields. Medium severity — could cause rendering gaps on the frontend.
- **System prompt correctly prohibits markdown fences** — but `_strip_fences` is still used as a safety net. ✅

### 4f. `backend/app/rag/ingest.py` (38 lines)

**What it does:** Reads PDFs from `data/sidbi_docs/`, chunks with `RecursiveCharacterTextSplitter`, stores in ChromaDB via native `chromadb.PersistentClient`.

**Issues:**
- **`RecursiveCharacterTextSplitter` expects langchain `Document` objects** — works with `PyPDFLoader` output. ✅
- **UUIDs generated per chunk** — deterministic if re-run? No, each run generates new UUIDs, creating duplicate chunks in ChromaDB. ⚠️ **Medium severity.** The `ingest` function should either clear the collection before adding, use content-hash-based IDs, or check for duplicates.
- **`langchain-community` deprecation warning** — `PyPDFLoader` from `langchain-community` triggers a deprecation notice. Should migrate to `pypdf` direct usage. Low urgency.

### 4g. `backend/app/rag/retrieve.py` (25 lines)

**What it does:** Module-level ChromaDB client + collection, `retrieve(query, k=3)` returns `{content, source}[]`.

**Issues:**
- **`_client.get_collection(name="sidbi_docs")` will raise if collection doesn't exist** — module-level initialization fails if `ingest.py` hasn't been run. The server won't start. ⚠️ **Medium severity.** Should handle `ValueError` (collection not found) with a fallback or clearer error.
- **`results["ids"][0]` assumes at least one result** — if `k=0` or no matches, this will crash with IndexError. `get_collection` may return empty results. Low (k=3 is hardcoded in the caller).

---

## 5. Frontend Review — `frontend/app/page.tsx` (287 lines)

**What it does:** Single-page React app with two "screens" (upload form + report display) managed by a `screen` state variable. No router.

### API URL
```ts
const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001/report";
```
✅ Correctly uses `NEXT_PUBLIC_API_URL` env var with localhost fallback.

### Error states
- **Network error (fetch fails)** — caught by `try/catch`, displayed as a red banner with "try again" button. ✅
- **Non-2xx response** — reads body text, throws with it. ✅
- **Malformed JSON** — `await res.json()` will throw `SyntaxError`, caught by the generic `catch`. Displayed as "Unknown error" unless the error message is helpful. Low — the error message won't indicate JSON parsing failure.
- **Large file** — no file size validation before upload. A very large photo or audio file could consume memory or hit backend limits. Low-medium.
- **Disallowed file types** — `accept="image/*"`, `accept="audio/*"`, `accept=".csv"` are advisory only; the user can select any file. Could be exploited but no security impact (backend validates independently).

### Edge cases
- **No inputs provided** — the "Generate Report" button is disabled (`!canSubmit`). ✅
- **Missing inputs on report screen** — renders an amber note with human-readable labels. ✅
- **`Band` type is `Band` (union of "Low"|"Moderate"|"Strong")** — safely narrows via `bandColor` switch. ✅
- **`report.business_type ?? "Not specified"`** — handles null. ✅
- **`report.evidence_summary` map** — relies on it being an array. If it's undefined, `.map()` will crash. ⚠️ **Medium severity.** Should default to `[]`.

### Code quality
- Single React component (~260 lines of JSX). Could benefit from splitting into `UploadForm` and `ReportScreen` components. Minor.
- Uses `URL.createObjectURL` for photo thumbnails but never calls `URL.revokeObjectURL` — **memory leak** on photos with many retakes. Low for field-officer use (few photos per session).

---

## 6. CORS Configuration

Current allow_origins in `backend/app/main.py`:
```python
allow_origins=[
    "http://localhost:3000",
    "https://hack-verse-psi.vercel.app",
],
allow_methods=["*"],
allow_headers=["*"],
```

- Localhost for development ✅
- Vercel production domain ✅
- `allow_methods=["*"]` — acceptably permissive for this API
- `allow_credentials` is not set (defaults to `False`) — fine, no auth cookies used
- **Missing**: `https://hack-verse-psi.vercel.app` is the only production origin listed. If the frontend is deployed on a custom domain later, this needs updating. Also no `http://127.0.0.1:3000` (only `localhost:3000`) — some dev setups use the IP directly.

**Verdict:** Safe and sufficient for current deployment. ✅

---

## 7. Environment Variables — Cross-Reference

### Env vars read in code (`os.getenv` / `os.environ.get` / `process.env`):

| Variable | Where Read | In `.env.example`? | In `README.md`? |
|----------|-----------|-------------------|-----------------|
| `OPENROUTER_API_KEY` | `vision_agent.py:9`, `synthesis_agent.py:10`, `voice_agent.py:9` | ✅ | ✅ (labelled as `your_key_here`) |
| `HF_TOKEN` | *(not read in code anymore)* | ✅ (`.env.example` — leftover) | ✅ (README mentions it) |
| `NEXT_PUBLIC_API_URL` | `page.tsx:5` | ❌ | ❌ |

**Mismatches:**
1. **`HF_TOKEN` in `.env.example` and README** — no code actually reads `HF_TOKEN` anymore. It was used for HuggingFace embeddings which have been replaced with ChromaDB ONNX embeddings. **Should be removed from `.env.example` and README.**
2. **`NEXT_PUBLIC_API_URL`** — used by the frontend but not documented in `.env.example` (which is backend-only) or README. Should be documented in the frontend section of README.

---

## 8. Known Limitations

1. **No fraud detection** — The system takes submitted evidence at face value. A field officer could submit fabricated photos or altered CSVs. No cross-referencing with bank records or credit bureaus.

2. **No authentication** — No user login, role management, or session handling. The API is fully open. Anyone who can reach the endpoint can submit reports.

3. **No live bank API integration** — Transaction analysis relies entirely on CSV uploads. No UPI/banking API integration for real-time verification.

4. **Cold-start delay** — ChromaDB's ONNX model (~79MB) downloads on first ingest/query if not cached. On Render free tier (ephemeral filesystem), this happens on every cold deploy. Whisper `base` model (~140MB on disk) also loads on first request. Combined could cause 10-30s cold start.

5. **Business type accuracy** — Depends heavily on voice transcription quality (Whisper `base` + potentially noisy field recordings). Mis-transcriptions directly affect the assessment output.

6. **Empty band values** — If the synthesis LLM returns an unexpected string for a band field (not "Low"/"Moderate"/"Strong"), the frontend's `bandColor()` function will return `undefined`, and the pill renders with no background/text color.

7. **Currency ambiguity** — All transaction amounts are treated as unitless numbers. For an Indian lender using SIDBI, amounts are likely INR but no currency label is attached.

8. **No retry logic** — OpenRouter calls fail immediately on network error. No exponential backoff. The entire `/report` pipeline fails if one agent's LLM call fails momentarily.

9. **No request size limits** — No `max_file_size` or `max_body_size` configuration. A maliciously large file could OOM the server.

---

## 9. Test Coverage

Based on inspection of the repository:

| Test Type | Status | Details |
|-----------|--------|---------|
| Unit tests | ❌ None | No test files (`test_*.py`, `*.test.ts`) exist anywhere in the repo |
| Integration tests | ❌ None | No automated pipeline tests |
| Manual end-to-end | ⚠️ Partial | `test_media/` has 2 photos, 1 WAV, 1 CSV — likely used for manual curl testing |
| RAG ingest | ✅ Verified | Ran successfully: "Ingested 33 chunks from 21 pages" |
| RAG retrieve | ✅ Verified | `POST /rag/query` returns top-3 chunks (verified via curl in earlier session) |
| Vision agent | ❌ Not tested | No evidence of running against actual OpenRouter |
| Voice agent | ❌ Not tested | `test_media/voicenote.wav` exists but no run evidence |
| Transaction agent | ❌ Not tested | `test_media/transactions.csv` exists but no run evidence |
| Synthesis agent | ❌ Not tested | Requires all other agents to produce output first |
| Full `/report` pipeline | ❌ Not tested | Never run end-to-end |
| Frontend | ❌ Not tested | No browser test, no headless test, no manual screenshot evidence |

**Conclusion:** The ingestion and retrieval pipeline has been verified manually. Everything downstream (vision → voice → transaction → synthesis → frontend) is code-complete but untested against real LLM calls. The `test_media/` fixtures exist for manual testing but were never used in a known successful end-to-end run.
