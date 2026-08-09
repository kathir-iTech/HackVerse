# HackVerse / Theligai — Full Codebase Audit & Remediation Plan

## Top-Level Overview

**Project:** HackVerse / Theligai — Multi-agent AI MSME Business Readiness Assessment System  
**Stack:** FastAPI (Python 3.11+) backend · Next.js 16 / React 19 / TypeScript 5 frontend  
**Scope:** Security audit, architecture review, bug detection, and prioritized remediation across all backend agents, API routes, frontend interactions, dependencies, and deployment configuration.  
**Approach:** Non-destructive audit first (this plan), then phased remediation sub-tasks ordered by severity.  
**Non-Goals:** Feature additions, UX redesign, database migration, CI/CD setup (tracked as Phase 4).

---

## Architecture Map

```
[Frontend — Vercel]
  page.tsx (single-page, React state machine)
    ├─ Screen: pin        → sends X-Officer-Pin header
    ├─ Screen: upload     → background-precomputes vision/voice
    ├─ Screen: report     → POST /report or POST /report/synthesize
    └─ Screen: history    → GET /reports · GET /vendors/{name}/history

[Backend — FastAPI on Render]
  main.py
    ├─ GET  /health
    ├─ GET  /reports                          ← UNPROTECTED
    ├─ GET  /vendors/{vendor_name}/history    ← UNPROTECTED
    ├─ GET  /reports/{report_id}              ← path-traversal risk
    ├─ POST /rag/query
    ├─ POST /agents/vision
    ├─ POST /agents/voice
    ├─ POST /report                           ← PIN-protected
    └─ POST /report/synthesize                ← PIN-protected
    │
    ├─ agents/
    │   ├─ vision_agent.py       → OpenRouter (Gemini 2.5 Flash)
    │   ├─ voice_agent.py        → faster-whisper + OpenRouter (Granite)
    │   ├─ transaction_agent.py  → pandas CSV/Excel parser
    │   ├─ synthesis_agent.py    → OpenRouter (Granite) + RAG context
    │   ├─ location_agent.py     → Nominatim reverse geocode
    │   ├─ anomaly_agent.py      → risk/completeness scoring
    │   └─ document_agent.py     → pypdf + Gemini vision fallback
    ├─ rag/
    │   ├─ ingest.py    → PDF → ChromaDB (ONNX all-MiniLM-L6-v2)
    │   └─ retrieve.py  → ChromaDB query (k=2)
    └─ utils/
        └─ privacy.py   → regex PII scrubber

[Storage — Filesystem (ephemeral on Render)]
  backend/chroma_db/        (vector embeddings)
  backend/report_cache/     (JSON reports, unbounded)
  backend/photo_hashes/     (image dedup hashes, unbounded)
```

---

## Findings Summary (Prioritized)

| # | Severity | Category | Issue | File |
|---|----------|----------|-------|------|
| 1 | 🔴 CRITICAL | Auth | `/reports` and `/vendors/…/history` endpoints have NO PIN requirement | `main.py:83,107` |
| 2 | 🔴 CRITICAL | Security | `vendor_name` and `report_id` path parameters used to construct file paths without sanitization (path traversal) | `main.py:109,132` |
| 3 | 🔴 CRITICAL | Auth | `verify_officer_pin` silently disables auth if `OFFICER_PIN` env var is not set | `main.py:24` |
| 4 | 🔴 CRITICAL | Privacy | Document agent extracts `entity_name`, `registration_number` but does NOT apply PII scrubbing before synthesis | `document_agent.py:315` |
| 5 | 🔴 CRITICAL | Security | Raw JSON evidence injected into LLM prompt without escaping — prompt injection via malicious CSV or voice note | `synthesis_agent.py:116,125` |
| 6 | 🟠 HIGH | DoS | No file size validation before `pd.read_csv()` / `pd.read_excel()` — server can OOM on large upload | `transaction_agent.py:47` |
| 7 | 🟠 HIGH | DoS | `faster-whisper.transcribe()` has no timeout — long audio blocks thread indefinitely | `voice_agent.py:65` |
| 8 | 🟠 HIGH | Reliability | API key (`OPENROUTER_API_KEY`) checked at module load; if missing, agents crash on first call with no clear message | `synthesis_agent.py:10`, `vision_agent.py:20`, `document_agent.py:12` |
| 9 | 🟠 HIGH | Supply Chain | All backend deps in `requirements.txt` are unversioned — breaking changes can silently reach production | `requirements.txt` |
| 10 | 🟠 HIGH | Reliability | Report cache and photo hash directories grow unbounded — disk exhaustion on long-running instance | `main.py:42-43` |
| 11 | 🟠 HIGH | Privacy | `/vendors/{vendor_name}/history` returns full vendor assessment history (PII, financial data) to unauthenticated callers | `main.py:107` |
| 12 | 🟠 HIGH | Reliability | RAG `retrieve.py` silently returns placeholder when ChromaDB is uninitialized — callers get no error signal | `rag/retrieve.py:11` |
| 13 | 🟡 MEDIUM | Validation | Inventory level classification in anomaly agent uses brittle keyword regex on free-form LLM text | `anomaly_agent.py:54` |
| 14 | 🟡 MEDIUM | Validation | Monthly date format in transaction agent uses `errors="coerce"` silently turning bad dates into NaT | `transaction_agent.py:68` |
| 15 | 🟡 MEDIUM | Validation | Coefficient of variation in transaction agent can produce Inf/extreme values when mean is near zero | `transaction_agent.py:172` |
| 16 | 🟡 MEDIUM | Error Handling | 6+ bare `except Exception: pass/return` blocks mask errors uniformly across agents | multiple agents |
| 17 | 🟡 MEDIUM | Deps | Both `pypdf` and `PyPDF2` listed; `langchain`, `langchain-openai`, `requests` appear unused | `requirements.txt` |
| 18 | 🟡 MEDIUM | Frontend | `URL.createObjectURL()` for photo previews never revoked — memory leak on multi-photo sessions | `page.tsx` |
| 19 | 🟡 MEDIUM | Frontend | No client-side file size validation — large files consumed by browser before backend rejects | `page.tsx` |
| 20 | 🟡 MEDIUM | Testing | Zero unit or integration tests across the entire codebase | all files |

---

## Sub-Tasks

---

### Sub-Task 1 — Protect Unguarded API Endpoints

**Intent:**  
Add `verify_officer_pin` dependency to the four data-access endpoints that currently have no authentication. This closes direct data exfiltration of vendor assessment history and cached reports without any credential.

**Expected Outcomes:**  
- `GET /reports`, `GET /vendors/{vendor_name}/history`, and `GET /reports/{report_id}` all return HTTP 401 when called without a valid `X-Officer-Pin` header.  
- The `/health` and `/rag/query` endpoints remain open (by design).  
- No change to request/response schema.

**Todo List:**  
1. Open `backend/app/main.py` and locate the three route decorators at lines ~83, ~107, and ~132.  
2. Add `dependencies=[Depends(verify_officer_pin)]` to each of those three routes.  
3. Verify the existing `/agents/vision` and `/agents/voice` standalone routes — confirm whether they should also require auth (likely yes; mark them accordingly).  
4. Manually test with and without the `X-Officer-Pin` header to confirm 401 response.

**Relevant Context:**  
- `main.py:24-29` — `verify_officer_pin()` dependency definition  
- `main.py:83` — `GET /reports`  
- `main.py:107` — `GET /vendors/{vendor_name}/history`  
- `main.py:132` — `GET /reports/{report_id}`

**Status:** [ ] pending

---

### Sub-Task 2 — Fix PIN Auth Bypass on Missing Environment Variable

**Intent:**  
`verify_officer_pin` currently returns early (allows all traffic) when `OFFICER_PIN` is not set. Change to fail-closed: if the env var is absent, raise HTTP 403 with a clear configuration error so operators know something is misconfigured rather than silently running unprotected.

**Expected Outcomes:**  
- If `OFFICER_PIN` is not set, every protected endpoint returns HTTP 403 `"Officer PIN not configured"`.  
- If `OFFICER_PIN` is set and the header matches, request proceeds.  
- If `OFFICER_PIN` is set and the header is wrong or missing, HTTP 401.

**Todo List:**  
1. Open `main.py:24-29`.  
2. Replace the early-return branch with `raise HTTPException(status_code=503, detail="Officer PIN not configured on server")`.  
3. Update the existing 401 branch to also cover a missing header (currently `None`).  
4. Update `.env.example` with a note: `# Required — server returns 503 if not set`.

**Relevant Context:**  
- `main.py:24-29` — current `verify_officer_pin` implementation  
- `.env.example` — environment variable documentation

**Status:** [ ] pending

---

### Sub-Task 3 — Patch Path Traversal in File-Based Routes

**Intent:**  
`vendor_name` and `report_id` URL parameters are used directly in file-system path construction. An attacker can craft a value like `../../etc/passwd` or `../other_vendor` to read arbitrary files outside the intended cache directories.

**Expected Outcomes:**  
- `vendor_name` accepts only alphanumeric characters, spaces, hyphens, and underscores. All other input returns HTTP 400.  
- `report_id` is validated as a valid UUID v4 string. Non-UUID values return HTTP 400.  
- Both validations happen before any filesystem access.

**Todo List:**  
1. Open `main.py`.  
2. Add a `_safe_vendor_name(name: str) -> str` helper that raises `HTTPException(400)` on any `..`, `/`, or `\` characters (or use `re.fullmatch` with an allow-list).  
3. Add a `_valid_report_id(rid: str)` helper that calls `uuid.UUID(rid)` in a try/except and raises `HTTPException(400)` on failure.  
4. Call both helpers at the top of the relevant route handlers.  
5. Test with `vendor_name=../../etc/passwd` and `report_id=../other` — expect 400.

**Relevant Context:**  
- `main.py:109` — `vendor_name` used in path  
- `main.py:132-139` — `report_id` used in path  
- Python `uuid` stdlib, `re` stdlib

**Status:** [ ] pending

---

### Sub-Task 4 — Scrub PII from Document Agent Extracted Fields

**Intent:**  
`document_agent.py` applies `scrub_pii()` to the raw PDF text before LLM parsing, but the *output* fields (`entity_name`, `registration_number`) bypass scrubbing and flow unfiltered into the synthesis prompt. A misclassified document (e.g., Aadhaar card mistaken for bank statement) could expose Aadhaar numbers to the synthesis LLM call.

**Expected Outcomes:**  
- All string values in `key_fields` inside `_tier2_vision()` and `_tier1_extract()` are passed through `scrub_pii()` before being returned.  
- Existing PII scrubbing on `raw_text` is preserved.  
- `registration_number` and `entity_name` values in the final synthesis payload have Aadhaar/PAN/phone patterns masked.

**Todo List:**  
1. Open `backend/app/agents/document_agent.py`.  
2. Identify all places where `key_fields` dict is constructed (lines ~315-322 and any equivalent in `_tier1_extract`).  
3. Wrap each string value in `key_fields` with `scrub_pii(value) if isinstance(value, str) else value`.  
4. Import `scrub_pii` if not already imported at the top of the file.  
5. Check `privacy.py` to confirm `scrub_pii` handles `None` gracefully (or add a guard).

**Relevant Context:**  
- `document_agent.py:315-322` — key_fields construction  
- `utils/privacy.py` — `scrub_pii()` implementation  
- `synthesis_agent.py:116,125` — where document fields flow next

**Status:** [ ] pending

---

### Sub-Task 5 — Harden LLM Prompt Against Injection

**Intent:**  
`synthesis_agent.py` builds the user-turn of the LLM prompt by f-string interpolating raw evidence dicts as JSON. A malicious actor can embed LLM-readable JSON or markdown fences inside a CSV cell, voice transcript, or document field that overrides the synthesis instructions.

**Expected Outcomes:**  
- All evidence objects are serialized into a single, clearly-delimited JSON wrapper before being appended to the prompt.  
- No raw string interpolation of user-controlled data into the narrative portion of the prompt.  
- LLM receives evidence in a structured envelope it cannot mistake for instruction text.

**Todo List:**  
1. Open `backend/app/agents/synthesis_agent.py`.  
2. Locate all `evidence_parts.append(f"[photos: ...]")` and similar lines (~116, ~125).  
3. Replace the per-source f-string fragments with a single `evidence_envelope = json.dumps({"photos": vision_result, "voice": voice_evidence, "transactions": transaction_result, ...}, ensure_ascii=False)`.  
4. Inject `evidence_envelope` into the prompt as a single labelled block: `\n---EVIDENCE (JSON)---\n{evidence_envelope}\n---END EVIDENCE---\n`.  
5. Update the system prompt to reference the envelope format so the LLM knows to parse it.  
6. Test with a malicious CSV containing an embedded JSON snippet in a cell value — confirm synthesis output is unchanged.

**Relevant Context:**  
- `synthesis_agent.py:116-175` — evidence assembly and prompt construction  
- `synthesis_agent.py:179-197` — LLM call and output parsing

**Status:** [ ] pending

---

### Sub-Task 6 — Add File Size Limits to Upload Handlers

**Intent:**  
No server-side limits exist on uploaded CSV, audio, or photo file sizes. A single large file can exhaust server memory (pandas CSV OOM) or block a thread indefinitely (Whisper on long audio). This also closes a simple denial-of-service vector.

**Expected Outcomes:**  
- CSV/Excel files larger than 50 MB are rejected with HTTP 413 before pandas loads them.  
- Audio files larger than 25 MB are rejected before Whisper processes them.  
- Photo files larger than 10 MB each are rejected before base64 encoding.  
- Client receives a clear error message describing the size limit.

**Todo List:**  
1. Open `backend/app/main.py` — find where `UploadFile` parameters are accepted for the `/report` and `/report/synthesize` routes.  
2. After saving each `UploadFile` to disk, add a size check using `os.path.getsize()` against the per-type limit constant.  
3. Add similar guards inside `transaction_agent.py:47` and `voice_agent.py:65` as defence-in-depth (agents are also callable standalone).  
4. Add client-side soft warnings in `page.tsx` when a selected file exceeds the same limits (browser `file.size` check) so the user gets instant feedback.

**Relevant Context:**  
- `main.py` — UploadFile parameters  
- `transaction_agent.py:47-58` — `pd.read_csv()` call  
- `voice_agent.py:65-75` — `model.transcribe()` call  
- `page.tsx` — file input `onChange` handlers

**Status:** [ ] pending

---

### Sub-Task 7 — Add Timeout to Whisper Transcription

**Intent:**  
`voice_agent._transcribe_audio()` calls `faster_whisper.model.transcribe()` synchronously. There is no upper bound on how long this can run. A very long or adversarially crafted audio file blocks the thread-pool worker indefinitely, degrading all concurrent requests.

**Expected Outcomes:**  
- Whisper transcription is bounded to a maximum of 120 seconds.  
- If the timeout fires, `process_voice()` returns a structured error dict with `"error": "transcription_timeout"` instead of hanging.  
- No impact on normal < 5-minute field recordings.

**Todo List:**  
1. Open `backend/app/agents/voice_agent.py`.  
2. Wrap the `model.transcribe()` call in a `concurrent.futures.ThreadPoolExecutor` future with a `timeout=120` on `.result()`.  
3. Catch `concurrent.futures.TimeoutError` and return `{"error": "transcription_timeout", "detail": "Audio exceeded maximum processing time"}`.  
4. Test with a synthetic long-duration audio file (or mock) to confirm timeout triggers.

**Relevant Context:**  
- `voice_agent.py:65-75` — `model.transcribe()` call  
- Python `concurrent.futures` stdlib

**Status:** [ ] pending

---

### Sub-Task 8 — Pin All Dependency Versions

**Intent:**  
Both `backend/requirements.txt` and `frontend/package.json` use unpinned versions (`^` or bare names). Any upstream library update — including a transient security patch that breaks an API — can silently break production. The `chromadb` library in particular has rewritten its storage format between minor versions.

**Expected Outcomes:**  
- `requirements.txt` has exact versions (`==`) for all direct dependencies.  
- `frontend/package.json` uses exact versions (no `^` or `~`) for all dependencies.  
- A `requirements.lock` or `pip-compile` output is generated and committed.  
- Duplicates (`PyPDF2`, clearly unused `langchain-openai`, `requests`, `langchain`) are removed.

**Todo List:**  
1. In the running environment, execute `pip freeze > requirements.lock` to capture current exact versions.  
2. Rewrite `requirements.txt` with `==` pinned versions, removing the four unused packages.  
3. Open `frontend/package.json` and remove `^` from all `dependencies` and `devDependencies` values.  
4. Run `npm install` to update `package-lock.json` with exact versions.  
5. Verify backend starts and frontend builds after pinning.

**Relevant Context:**  
- `backend/requirements.txt`  
- `frontend/package.json`

**Status:** [ ] pending

---

### Sub-Task 9 — Fix Report Cache and Photo Hash Unbounded Growth

**Intent:**  
`backend/report_cache/` and `backend/photo_hashes/` directories accumulate JSON files indefinitely. On Render's free tier (or any deployment), this will eventually exhaust disk space. There is no cleanup, TTL, or maximum-entries policy.

**Expected Outcomes:**  
- A `_evict_cache(directory, max_entries)` utility is added to `main.py`.  
- After writing a new report to `report_cache/`, eviction runs and removes the oldest files if count exceeds a configurable `REPORT_CACHE_MAX` (default 500).  
- Same policy applied to `photo_hashes/` directory.  
- Existing cached reports older than 30 days are eligible for eviction.

**Todo List:**  
1. Open `main.py` and find where reports are written to `report_cache/`.  
2. Write `_evict_cache(cache_dir: str, max_entries: int = 500)` that sorts files by `mtime` and deletes oldest until `len <= max_entries`.  
3. Call `_evict_cache(REPORT_CACHE_DIR)` and `_evict_cache(PHOTO_HASH_DIR)` after each write.  
4. Add `REPORT_CACHE_MAX` and `HASH_CACHE_MAX` as configurable constants at top of `main.py`.

**Relevant Context:**  
- `main.py:42-43` — cache directory constants  
- `main.py` — report write locations

**Status:** [ ] pending

---

### Sub-Task 10 — Harden API Key Handling Across All Agents

**Intent:**  
Multiple agents check `OPENROUTER_API_KEY` at module import time with inconsistent patterns (`os.environ.get` vs `os.getenv`). Some print a warning and continue with an empty key (fails at the first real call with a cryptic auth error); others may crash the server on import. Centralise the check and fail with a clear message at call time rather than silently corrupting state.

**Expected Outcomes:**  
- A single `get_openrouter_client()` factory in a shared `utils/llm.py` returns a configured `OpenAI` client.  
- If the key is absent, `get_openrouter_client()` raises a `ValueError` with a clear message.  
- Each agent calls `get_openrouter_client()` lazily (inside the handler function), so a missing key produces an `HTTP 500` with `"detail": "API key not configured"` rather than an import error or silent empty-key failure.  
- All direct `os.environ.get("OPENROUTER_API_KEY")` blocks are removed from individual agents.

**Todo List:**  
1. Create `backend/app/utils/llm.py` with `get_openrouter_client()`.  
2. Update `vision_agent.py`, `voice_agent.py`, `synthesis_agent.py`, `document_agent.py` to import and call `get_openrouter_client()` inside their handler functions.  
3. Remove the top-level API key checks from each agent file.  
4. Add a startup check in `main.py` using `@app.on_event("startup")` that calls `get_openrouter_client()` once and logs success/failure (but does NOT exit — let it fail per-request instead).

**Relevant Context:**  
- `vision_agent.py:20-23`  
- `voice_agent.py:17`  
- `synthesis_agent.py:10-13`  
- `document_agent.py:12-15`  
- `utils/privacy.py` — example of existing utils pattern

**Status:** [ ] pending

---

### Sub-Task 11 — Fix CV Overflow and Magic-Number Thresholds in Transaction Agent

**Intent:**  
The coefficient of variation (CV) calculation divides by the daily net mean. If the mean is a very small non-zero number (e.g., 0.001), the CV becomes astronomically large (Inf-adjacent), causing an incorrect "extreme volatility" classification. Several other thresholds (50000, 500000, ratio > 5) are magic numbers with no documentation.

**Expected Outcomes:**  
- CV is clamped to a maximum of `10.0` (1000%) with a comment explaining the cap.  
- Monthly date coercion warnings are surfaced via a log message when NaT values are produced.  
- All threshold constants in `transaction_agent.py` and `anomaly_agent.py` are extracted to named constants at the top of each file with inline comments explaining the business rationale.

**Todo List:**  
1. Open `transaction_agent.py:172` — add `cv = min(cv, 10.0)` after the existing guard.  
2. Open `transaction_agent.py:68` — after `pd.to_datetime(errors="coerce")`, log a warning if the resulting Series contains any `NaT` values.  
3. Open `anomaly_agent.py:9-19` — extract `HIGH_VOLATILITY_THRESHOLD`, `MIN_INFLOW_THRESHOLD`, `MAX_EXPENSE_RATIO`, `TENURE_MISMATCH_TOLERANCE` as module-level constants.  
4. Add a comment next to each constant citing the business rule or source document it derives from.

**Relevant Context:**  
- `transaction_agent.py:68,172,195`  
- `anomaly_agent.py:9-19, 83, 88, 104, 111, 125`

**Status:** [ ] pending

---

### Sub-Task 12 — Fix Frontend Memory Leak and Add Client-Side Validation

**Intent:**  
Photo previews in `page.tsx` create object URLs via `URL.createObjectURL()` but never call `URL.revokeObjectURL()`. Over a session with many photo uploads, this leaks memory. Separately, there is no client-side file size check — users only discover oversized files after uploading.

**Expected Outcomes:**  
- Object URLs are revoked in a `useEffect` cleanup or when photos are removed.  
- File picker `onChange` handlers validate file size before adding to state and show an inline warning for files exceeding the per-type limit.  
- No functional change to the upload or preview flow.

**Todo List:**  
1. Open `frontend/app/page.tsx`.  
2. Find all calls to `URL.createObjectURL()` and store the returned URLs in a ref or state alongside the `File`.  
3. Add a `useEffect` that returns a cleanup function calling `URL.revokeObjectURL()` for all stored URLs.  
4. In the photo `onChange` handler, add `if (file.size > 10 * 1024 * 1024) { showWarning(...); return; }`.  
5. Add equivalent size checks for audio (25 MB) and CSV (50 MB) inputs.

**Relevant Context:**  
- `frontend/app/page.tsx` — file input handlers and photo preview rendering

**Status:** [ ] pending

---

## Implementation Order

```
Phase 1 — Critical (ship before any user traffic)
  Sub-Task 1  Protect unguarded endpoints
  Sub-Task 2  Fix PIN auth bypass
  Sub-Task 3  Patch path traversal
  Sub-Task 4  Scrub PII from document fields
  Sub-Task 5  Harden LLM prompt injection

Phase 2 — High (required before production deployment)
  Sub-Task 6  File size limits
  Sub-Task 7  Whisper timeout
  Sub-Task 8  Pin dependency versions
  Sub-Task 9  Cap cache growth
  Sub-Task 10 Centralise API key handling

Phase 3 — Medium (next sprint)
  Sub-Task 11 CV overflow and magic numbers
  Sub-Task 12 Frontend memory leak and client validation
```

---

## Open Questions for Review

1. Should `/agents/vision` and `/agents/voice` (standalone endpoints) also require PIN auth, or are they intended as public preview APIs?  
2. For the PIN auth bypass fix (Sub-Task 2): should a missing `OFFICER_PIN` env var return HTTP 503 (server misconfiguration) or HTTP 403 (auth refused)? The distinction affects monitoring alerting.  
3. The `report_cache` and `photo_hashes` directories are ephemeral on Render's free tier. Is a migration to a persistent store (e.g., Supabase, S3) in scope for this engagement, or is that a Phase 4 item?  
4. For Sub-Task 5 (prompt injection), should the system prompt also be updated to explicitly tell the LLM to ignore JSON-like structures embedded in evidence fields? This is defence-in-depth beyond structural escaping.  
5. Is there any compliance requirement (DPIIT, RBI data localisation) that affects where reports can be stored or which LLM provider can be used?
Here is the full audit report and plan. Let me walk you through everything.
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ## Architecture Overview
  ┌───────────────────────────────────────────────────────────┐
  │                                                           │
  │                     Frontend — Vercel                     │
  │                          page.tsx                         │
  │                   ReactO19/rrNexttjs 16                   │
  │                 GPOS/verepor/.../thesize                  │
  └───────────────────X-Officer-PinHheader────────────────────┘
  ┌───────────────────────────────────────────────────────────┐
  │                                                           │
  │                     Backend — FastAPI                     │
  │                          main.py                          │
  │                          9 routes                         │
  │                                                           │
  └─────────────────────────────▼─────────────────────────────┘           ▼                       ▼                       ▼                     ▼
  ┌─────────────────────────────┼─────────────────────────────┬─┬─────────┬─────────┬─┬───────────┬──────────┬─┬──────────┬─────────┬─┬─────────┬─────────
  │                                                           │ │                   │ │                      │ │                    │ │
  │                                                           │ │                   │ │                      │ │                    │ │
  │                      vision_agent.py                      │ │   voice_agent.py  │ │ transaction_agent.py │ │ synthesis_agent.py │ │ location_agent.py
  │                   OpenRouter Gemini 2.5                   │ │ Whisper + Granite │ │  pandas CSV parser   │ │ OpenRouter Granite │ │     Nominatim
  │                                                           │ │                   │ │                      │ │                    │ │
  └───────────────────────────────────────────────────────────┘ └───────────────────┘ └──────────────────────┘ └──────────┬─────────┘ └───────────────────
  ┌───────────────────────────────────────────────────────────┐                                                           │
  │                                                           │                                                           │
  │                                                           │                                                           │
  │                   rag/ingest + retrieve                   │◄──────────────────────────────────────────────────────────┘
  │                      ChromaDB + ONNX                      │
  │                                                           │
  └───────────────────────────────────────────────────────────┘
  [mermaid diagram cropped to terminal width]
  style FE fill:#1e40af,color:#fff
  style BE fill:#065f46,color:#fff
  style CACHE fill:#7f1d1d,color:#fff


  ---
  ## 🔴 Critical Findings (5 issues — fix before any user traffic)
  ┌───┬────────────────────────────────────────────────────────────────────────────────────────────────────────┬────────────────────┬──────────┐
  │ # │ Issue                                                                                                  │ File               │ Line     │
  ├───┼────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┼──────────┤
  │ 1 │ GET /reports & GET /vendors/.../history have zero authentication — any caller gets full vendor history │ main.py            │ 83, 107  │
  ├───┼────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┼──────────┤
  │ 2 │ verify_officer_pin silently disables auth if OFFICER_PIN env var is not set                            │ main.py            │ 24       │
  ├───┼────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┼──────────┤
  │ 3 │ vendor_name and report_id URL params fed directly to os.path.join — path traversal                     │ main.py            │ 109, 132 │
  ├───┼────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┼──────────┤
  │ 4 │ Document agent extracts entity_name, registration_number but skips PII scrubbing before synthesis      │ document_agent.py  │ 315      │
  ├───┼────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────┼──────────┤
  │ 5 │ Evidence JSON f-string-interpolated directly into LLM prompt — prompt injection via crafted CSV/audio  │ synthesis_agent.py │ 116, 125 │
  └───┴────────────────────────────────────────────────────────────────────────────────────────────────────────┴────────────────────┴──────────┘

  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ## 🟠 High Findings (6 issues — required before production deployment)
  ┌────┬────────────────────────────────────────────────────────────────────────────────────────────────┬─────────────────────────────────────┐
  │ #  │ Issue                                                                                          │ File                                │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
  │ 6  │ No file size limit before pd.read_csv() — OOM denial of service                                │ transaction_agent.py                │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
  │ 7  │ faster-whisper.transcribe() has no timeout — long audio blocks thread forever                  │ voice_agent.py                      │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
  │ 8  │ All backend deps unpinned in requirements.txt — breaking changes hit production silently       │ requirements.txt                    │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
  │ 9  │ report_cache/ and photo_hashes/ directories grow unbounded — disk exhaustion                   │ main.py                             │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
  │ 10 │ API key checked at module-load with inconsistent patterns; missing key produces cryptic errors │ vision_agent.py, synthesis_agent.py │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────────┤
  │ 11 │ RAG retrieve.py silently returns placeholder on ChromaDB failure — no error signal to callers  │ retrieve.py                         │
  └────┴────────────────────────────────────────────────────────────────────────────────────────────────┴─────────────────────────────────────┘

  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ## 🟡 Medium Findings (6 issues — next sprint)
  ┌────┬────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ #  │ Issue                                                                                          │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 12 │ CV calculation in transaction agent produces Inf/extreme values when daily mean ≈ 0            │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 13 │ URL.createObjectURL() for photo previews never revoked — memory leak on multi-photo sessions   │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 14 │ No client-side file size validation — large files consumed by browser silently                 │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 15 │ 6+ bare except Exception: pass blocks mask errors uniformly across agents                      │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 16 │ PyPDF2, langchain-openai, requests, langchain are unused dependencies (bloat + attack surface) │
  ├────┼────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ 17 │ Zero unit or integration tests across the codebase                                             │
  └────┴────────────────────────────────────────────────────────────────────────────────────────────────┘

  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ## Remediation Plan (12 sub-tasks)
  The plan has been written to codebase-audit-plan.md.
  Phase 1 — Critical (do first)
    Sub-Task 1  → Protect unguarded endpoints
    Sub-Task 2  → Fix PIN auth bypass
    Sub-Task 3  → Patch path traversal
    Sub-Task 4  → Scrub PII from document fields
    Sub-Task 5  → Harden LLM prompt injection

  Phase 2 — High (before production)
    Sub-Task 6  → File size limits
    Sub-Task 7  → Whisper timeout
    Sub-Task 8  → Pin dependency versions
    Sub-Task 9  → Cap cache growth
    Sub-Task 10 → Centralise API key handling

  Phase 3 — Medium (next sprint)
    Sub-Task 11 → CV overflow and magic-number constants
    Sub-Task 12 → Frontend memory leak + client-side validation
  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ## Before I finalise this plan, I need your answers on 5 open questions:
  1. Standalone agent auth: Should POST /agents/vision and POST /agents/voice also require the X-Officer-Pin header, or are they intentionally public prev
  iew APIs?
  2. Missing-PIN failure mode: When OFFICER_PIN is not set in the environment, should protected endpoints return HTTP 503 (server misconfigured) or HTTP 4
  03 (auth refused)? This affects how monitoring alerts fire.
  3. Persistent storage: The report_cache/ and chroma_db/ directories are ephemeral on Render's free tier — every cold restart loses all data. Is migratin
  g to a persistent store (S3, Supabase, or a managed vector DB) in scope for this remediation, or is that a later phase?
  4. Prompt injection defence depth: For Sub-Task 5, beyond structurally wrapping evidence in a JSON envelope, should the system prompt also be updated to
   explicitly instruct the LLM to treat all content inside ---EVIDENCE--- as untrusted data and ignore any embedded instructions?
  5. Compliance scope: Are there active DPIIT data-localisation requirements or RBI guidelines that govern where vendor PII and transaction data may be st
  ored or which LLM provider may process it? This affects whether the current OpenRouter (US-hosted) routing is compliant.


 ╭────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
 │ ❯                                                                                                                                                      │
 ╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
  Plan Mode · 31k / 270k (11%) · 0.66 🅞



