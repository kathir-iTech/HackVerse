# Project Summary — HackVerse

---

## 1. Project Overview

**Name:** HackVerse — SIDBI Business Readiness Report

**One-line description:** A multi-agent AI system that ingests photos, voice notes, and transaction CSVs gathered by a field officer during an MSME vendor visit and produces a structured lending-readiness assessment referencing SIDBI/RBI schemes.

**Problem it solves:** Traditional MSME lending requires lengthy manual paperwork and subjective judgment by loan officers. This tool digitises the field evidence collection process and uses LLMs to produce a consistent, evidence-based assessment, reducing turnaround time for micro-loan decisions.

**Target user:** Field officers of banks/NBFCs working with SIDBI who visit small vendors, collect evidence (shop photos, voice recordings of the business owner, transaction history), and need a standardised report to attach to a loan application.

---

## 2. Architecture

```
User (browser)                  Field Officer (browser)
      │                               │
      │  HTTP upload (photos,          │
      │  voice, CSV)                   │
      ▼                               │
┌─────────────────┐                   │
│   Next.js 16    │                   │
│  (Vercel)       │                   │
│  page.tsx       │                   │
│  upload form /  │                   │
│  report screen  │                   │
└──────┬──────────┘                   │
       │ POST /report (multipart)     │
       ▼                              │
┌─────────────────────────────────────┴──┐
│           FastAPI (Render)             │
│           main.py                      │
│                                        │
│  ┌──────────┬───────────┬───────────┐  │
│  │ Vision   │ Voice     │ Txn       │  │
│  │ Agent    │ Agent     │ Agent     │  │
│  │ (LLM)    │ (Whisper  │ (pandas)  │  │
│  │          │  + LLM)   │           │  │
│  └────┬─────┴─────┬─────┴─────┬─────┘  │
│       │           │           │        │
│       ▼           ▼           ▼        │
│  ┌─────────────────────────────────┐   │
│  │         ChromaDB (RAG)          │   │
│  │         retrieve.py             │   │
│  └──────────────┬──────────────────┘   │
│                 ▼                      │
│  ┌─────────────────────────────────┐   │
│  │       Synthesis Agent (LLM)     │   │
│  │       synthesize_report()       │   │
│  └──────────────┬──────────────────┘   │
│                 ▼                      │
│         Structured JSON report         │
└──────────────────────┬─────────────────┘
                       │
                       ▼
              Rendered in browser
```

### Components

| Component | File(s) | What it does |
|-----------|---------|-------------|
| **Frontend** | `frontend/app/page.tsx` | Single-page React app. Upload form accepts photos (jpeg/png), voice note (wav/mp3), transaction CSV. Report screen displays band pills, assessment, scheme note, evidence list. No router — state-driven screen toggle. |
| **FastAPI server** | `backend/app/main.py` | Routes HTTP requests. `/report` endpoint dispatches three agents concurrently via `asyncio.gather`, runs RAG retrieval, calls synthesis, returns JSON. |
| **Vision Agent** | `backend/app/agents/vision_agent.py` | Base64-encodes each photo, sends to OpenRouter `google/gemini-2.5-flash` for factual description (inventory, shop condition, activity). Then sends all descriptions to the same model for a cross-image summary. |
| **Voice Agent** | `backend/app/agents/voice_agent.py` | Loads Whisper `base` model (singleton, CPU int8), transcribes audio file, sends transcript to OpenRouter `ibm-granite/granite-4.1-8b` for structured JSON extraction (business type, products, years operating, location). |
| **Transaction Agent** | `backend/app/agents/transaction_agent.py` | Reads CSV with pandas, normalises column names (date/type/amount variants, separate debit/credit columns), infers direction from sign or separate columns, computes inflow/outflow totals, volatility (CV of daily net), month-over-month trend (linear slope). |
| **ChromaDB (RAG)** | `backend/app/rag/ingest.py`, `backend/app/rag/retrieve.py` | `ingest.py`: reads PDFs from `data/sidbi_docs/`, chunks with `RecursiveCharacterTextSplitter` (800 chars, 100 overlap), stores in ChromaDB with ONNX `all-MiniLM-L6-v2` embeddings. `retrieve.py`: module-level ChromaDB client, queries top-3 chunks by similarity. |
| **Synthesis Agent** | `backend/app/agents/synthesis_agent.py` | Aggregates vision/voice/transaction results + RAG context, sends to OpenRouter `ibm-granite/granite-4.1-8b` with a strict system prompt, parses returned JSON into the final assessment report. |

---

## 3. Tech Stack

### Frontend
| Technology | Version | Purpose |
|-----------|---------|---------|
| Next.js | 16.2.10 | React framework (static export via Vercel) |
| React | 19.2.4 | UI library |
| Tailwind CSS | 4.x | Utility-first styling |
| TypeScript | 5.x | Type safety |

### Backend
| Technology | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11+ | Runtime |
| FastAPI | latest | Web framework (ASGI) |
| Uvicorn | latest | ASGI server |
| langchain-community | latest | PyPDFLoader for PDF parsing |
| langchain-text-splitters | latest | RecursiveCharacterTextSplitter for chunking |
| chromadb | latest | Vector database (ONNX embedding, persistent) |
| pypdf | latest | PDF parsing backend |
| pandas | latest | CSV transaction analysis |
| numpy | latest | Numerical computations (volatility, trends) |
| faster-whisper | latest | Local speech-to-text (CPU, int8 quantised) |
| openai | latest | OpenRouter API client (OpenAI-compatible) |
| python-dotenv | latest | `.env` file loading |
| python-multipart | latest | File upload parsing |

### AI Models
| Model | Provider | Used By | Purpose |
|-------|----------|---------|---------|
| `google/gemini-2.5-flash` | OpenRouter | Vision Agent | Image description + cross-image summary |
| `ibm-granite/granite-4.1-8b` | OpenRouter | Voice Agent, Synthesis Agent | JSON extraction from transcripts; final report synthesis |
| `Systran/faster-whisper` (base) | Local (CPU) | Voice Agent | Speech-to-text transcription |
| `all-MiniLM-L6-v2` (ONNX) | ChromaDB (local) | RAG pipeline | Text embedding for similarity search |

### Deployment
| Component | Platform | URL |
|-----------|----------|-----|
| Frontend | Vercel | `https://hack-verse-psi.vercel.app` |
| Backend | Render (free tier) | *(not yet deployed — code assumes `http://127.0.0.1:8001`)* |

### Environment Variables
| Variable | Used By | Required? |
|----------|---------|-----------|
| `OPENROUTER_API_KEY` | `vision_agent.py`, `voice_agent.py`, `synthesis_agent.py` | Yes |
| `NEXT_PUBLIC_API_URL` | `page.tsx` frontend | No (defaults to `http://127.0.0.1:8001/report`) |

---

## 4. Workflow (Trace of One Request)

1. **User uploads files** via `page.tsx` upload form (photos + voice + CSV)
2. **`page.tsx` `handleSubmit()`** creates `FormData` with all files, calls `fetch(API, { method: "POST", body: fd })` where `API` = env var or `http://127.0.0.1:8001/report`
3. **`main.py:report()`** receives `photos: List[UploadFile]`, `audio: UploadFile`, `transactions: UploadFile`
4. **`_run_agent()`** is called three times — once per input type — creating coroutines:
   - `vision_coro = _run_agent("vision", photos, False, analyze_photos, timings)`
   - `voice_coro = _run_agent("voice", audio, True, process_voice, timings)`
   - `txn_coro = _run_agent("transactions", transactions, True, analyze_transactions, timings)`
5. **`_run_agent()`** writes each file to a temp file, calls the handler function via `asyncio.to_thread()`, cleans up temp files, and records timing
6. **`asyncio.gather()`** runs the three non-None coroutines concurrently:
   - **Vision**: `vision_agent.py:analyze_photos()` → for each photo: base64 encode → OpenRouter `google/gemini-2.5-flash` → description; then all descriptions → same model → summary → `{"per_image": [...], "summary": "..."}`
   - **Voice**: `voice_agent.py:process_voice()` → Whisper `base` transcribe → OpenRouter `ibm-granite/granite-4.1-8b` → JSON extraction → `{"transcript": "...", "extracted": {...}, "label": "officer observation, unverified"}`
   - **Transactions**: `transaction_agent.py:analyze_transactions()` → `pd.read_csv` → column normalisation → direction inference → compute inflow/outflow/count/avg/volatility/trend → `{"total_inflow": X, "total_outflow": Y, "transaction_count": N, "average_transaction": Z, "volatility": "low"|"moderate"|"high", "trend": "increasing"|"stable"|"decreasing"}`
7. **`main.py`** classifies each result as present (no error) or missing/error, building `missing` and `input_errors` lists
8. **`retrieve.py:retrieve("MSME working capital lending guidance", k=3)`** queries ChromaDB → returns `[{"content": "...", "source": "..."}]`
9. **`synthesis_agent.py:synthesize_report()`** receives all agent results + RAG context, builds a prompt with evidence strings, calls OpenRouter `ibm-granite/granite-4.1-8b`, strips markdown fences, parses JSON
10. **`main.py`** merges `missing_inputs`, `input_errors`, `_timings` into the report dict, returns JSON to frontend
11. **`page.tsx`** receives JSON, sets `report` state, switches to report screen; renders band pills, assessment box, scheme note, evidence list, missing-inputs warning

---

## 5. API Endpoints

| Method | Path | What it does | Input | Output |
|--------|------|-------------|-------|--------|
| `GET` | `/health` | Health check | None | `{"status": "ok"}` |
| `POST` | `/rag/query` | Query the RAG index | `{"query": "..."}` JSON | `{"query": "...", "results": [{"content", "source"}]}` |
| `POST` | `/agents/vision` | Run vision agent standalone | `files` (multipart, 1+ images) | `{"per_image": [...], "summary": "..."}` |
| `POST` | `/agents/voice` | Run voice agent standalone | `file` (multipart, 1 audio) | `{"transcript": "...", "extracted": {...}, "label": "..."}` |
| `POST` | `/report` | Full pipeline — run all agents + RAG + synthesis | `photos` (multipart, 0+), `audio` (0-1), `transactions` (0-1 CSV) | Structured assessment JSON (see §6) |

---

## 6. Data Flow (Input/Output Shapes)

### Vision Agent
```
Input:  list of image file paths (str[])
Output: {
  "per_image": [{"file": "photo1.jpg", "description": "Visible inventory includes..."}],
  "summary": "The descriptions show similar inventory of packaged goods across checkpoints..."
}
```

### Voice Agent
```
Input:  single audio file path (str)
Output: {
  "transcript": "i run a grocery shop for the past 10 years...",
  "extracted": {
    "business_type": "grocery retail",
    "products": "groceries, packaged goods",
    "years_operating": "10",
    "location": "chennai"
  },
  "label": "officer observation, unverified"
}
```

### Transaction Agent
```
Input:  single CSV file path (str)
Output: {
  "total_inflow": 450000.0,
  "total_outflow": 320000.0,
  "transaction_count": 145,
  "average_transaction": 3103.45,
  "volatility": "moderate",
  "trend": "increasing"
}
```

### RAG Retrieve
```
Input:  query string, k=int
Output: [{"content": "chunk text...", "source": "sidbi_direct_finance.pdf"}, ...]
```

### Synthesis Agent (→ Final Report)
```
Input:  vision_result (dict|None), voice_result (dict|None),
        transaction_result (dict|None), rag_context (list[dict])
Output: {
  "business_type": "grocery retail" | null,
  "revenue_consistency_band": "Low" | "Moderate" | "Strong",
  "inventory_observation_band": "Low" | "Moderate" | "Strong",
  "digital_activity_band": "Low" | "Moderate" | "Strong",
  "relevant_scheme_note": "Based on SIDBI guidelines, this business may qualify for...",
  "assessment_band": "Further assessment required" | "Suitable for micro-loan assessment" | "Suitable for higher assessment range",
  "evidence_summary": ["Business owner reported 10 years in grocery retail", ...],
  "missing_inputs": ["photos", "voice", "transactions"]
}
```

### Merged by main.py (additional keys added)
```
{
  ...synthesis output...,
  "missing_inputs": [...],
  "input_errors": [...],
  "_timings": {"vision": 4.2, "voice": 6.1, "transactions": 0.3, "rag": 0.1, "synthesis": 3.5}
}
```

---

## 7. Deployment

### Frontend (Vercel)
- **Live URL:** `https://hack-verse-psi.vercel.app`
- **Env var needed:** `NEXT_PUBLIC_API_URL` — set to the Render backend URL once deployed
- **Build command:** `npm run build`
- **Output:** Static export served by Vercel edge

### Backend (Render — planned, not yet deployed)
- **Live URL:** *(not deployed yet — code targets `http://127.0.0.1:8001`)*
- **Env var needed:** `OPENROUTER_API_KEY`
- **Start command:** `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8001`
- **Pre-deploy step:** Run `python -m app.rag.ingest` once to populate ChromaDB (Render ephemeral disk means this runs on every deploy — ONNX model will also redownload on cold start)
- **Known constraint:** ChromaDB is file-based (`backend/chromadb/`); on Render free tier, data is ephemeral and lost on restart. For production, ChromaDB should point to a persistent volume or use a hosted vector DB.

### Shared
- **CORS:** Backend explicitly allows `http://localhost:3000` and `https://hack-verse-psi.vercel.app`
- **Backend port:** 8001 (internally)

---

## 8. Current Status

### Working and Verified
- ✅ RAG PDF ingestion — 33 chunks from 21 pages, stored in ChromaDB with ONNX all-MiniLM-L6-v2
- ✅ RAG retrieval — returns top-3 chunks
- ✅ `/health`, `/rag/query`, `/agents/vision`, `/agents/voice` routes exist and respond
- ✅ All agent code is complete and importable without syntax errors
- ✅ Frontend renders both upload form and report screens
- ✅ CORS configured for localhost + Vercel
- ✅ API URL uses env var with fallback
- ✅ CSRF protection: not needed (no cookies/auth)
- ✅ Repository is pushed to GitHub (`https://github.com/kathir-iTech/HackVerse`)
- ✅ .gitignore covers env, caches, logs, build artifacts

### Code-Complete but Not End-to-End Tested
- ⚠️ Full `/report` pipeline has never been run with real OpenRouter calls
- ⚠️ Vision agent — OpenRouter `google/gemini-2.5-flash` calls untested
- ⚠️ Voice agent — Whisper transcription + OpenRouter extraction untested
- ⚠️ Transaction agent — CSV parsing logic untested against real-world bank CSVs
- ⚠️ Synthesis agent — never invoked with real agent outputs

### Explicitly Out of Scope / Not Built
- ❌ No user authentication or session management
- ❌ No database — all state is per-request; no report persistence
- ❌ No fraud detection — evidence is taken at face value
- ❌ No live bank API / UPI / credit bureau integration
- ❌ No report PDF generation or export
- ❌ No offline mode — requires internet for OpenRouter calls
- ❌ No file size limits on uploads
- ❌ No retry logic for LLM API failures
- ❌ No rate limiting
- ❌ No logs/audit trail of submitted reports
- ❌ No CI/CD pipeline
- ❌ No unit tests or integration tests
