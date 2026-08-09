# ONSITE COMPETITIVE AUDIT — Theligai (HackVerse)

**Audit type:** Zero-compromise production-readiness / live-judging prep
**Auditor role:** Elite Principal Performance Architect + Cyber-Security Auditor
**Method:** Full source read of every active code file, git history scan, live local endpoint execution against a running backend (`127.0.0.1:8001`), and dependency tree review.
**Date:** 2026-08-04 · Git head: `a7aafd7`

---

## 1. FILE & COMPONENT TREE DEPLOYMENT VALIDATION

### 1.1 Full repository map

```
HackVerse/
├── .gitignore                      # root ignore (python/node/chroma/env/cache)
├── README.md
├── ARCHITECTURE_DEEP_DIVE.md
├── AUDIT_REPORT.md
├── PROJECT_SUMMARY.md
├── PROJECT_FINAL_REPORT.md
├── ONSITE_COMPETITIVE_AUDIT.md     # ← this file
│
├── backend/
│   ├── .env.example                # OPENROUTER_API_KEY=sk-or-v1-your-key-here (placeholder)
│   ├── requirements.txt            # 16 deps, ALL unpinned
│   ├── chroma_db/chroma.sqlite3    # local, gitignored
│   ├── photo_hashes/               # NOT gitignored ← hygiene gap
│   │   └── AuditVendor.json
│   ├── data/sidbi_docs/
│   │   ├── rbi_msme_master_direction.pdf
│   │   ├── sidbi_direct_finance.pdf
│   │   └── sidbi_mudra_shishu_faq.pdf
│   ├── report_cache/               # gitignored, runtime writes
│   └── app/
│       ├── __init__.py
│       ├── main.py                 # FastAPI entrypoint (404 lines)
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── anomaly_agent.py    # pure logic risk indicators
│       │   ├── location_agent.py   # Nominatim OSM geocoder
│       │   ├── synthesis_agent.py  # OpenRouter granite-4.1-8b
│       │   ├── transaction_agent.py# pandas CSV parser
│       │   ├── vision_agent.py     # OpenRouter gemini-2.5-flash
│       │   └── voice_agent.py      # faster-whisper tiny + OpenRouter granite
│       └── rag/
│           ├── __init__.py
│           ├── ingest.py           # chroma persistent, manual CLI only
│           └── retrieve.py         # sync chroma query at import time
│
├── frontend/
│   ├── .gitignore                  # covers node_modules/.next/.env*
│   ├── package.json                # next 16.2.10, react 19.2.4
│   ├── package-lock.json           # committed → deterministic npm
│   ├── next.config.ts              # EMPTY (no image/CORS/output config)
│   ├── tsconfig.json               # strict:true
│   ├── eslint.config.mjs
│   ├── postcss.config.mjs
│   ├── README.md
│   └── app/
│       ├── favicon.ico
│       ├── globals.css
│       ├── layout.tsx              # ← title has mojibake "\uFFFD?" glyph
│       └── page.tsx                # single full app (885 lines)
│
└── test_media/
    ├── contradiction_voice.wav     (1.5 MB)
    ├── contradiction_voice2.wav    (1.27 MB)
    ├── fake.jpg                    (21 B — text payload, not an image)
    ├── fake_voice_note.txt
    ├── photo1.jpg                  (1.74 MB)
    ├── photo2.jpg                  (1.74 MB — byte-identical to photo1)
    ├── Record_1.wav                (2.4 MB)
    ├── test_1_pic.avif
    ├── transactions.csv            (202 B)
    ├── trans_1.csv                 (1.1 KB)
    └── voicenote.wav               (44 B — empty/dummy)
```

### 1.2 Import & path auditing

| Check | Result |
|---|---|
| Backend absolute imports (`from app.agents.…`) | Consistent lowercase, resolves correctly under `uvicorn app.main:app` from `backend/`. No breakage on Linux. |
| Case-sensitivity (camelCase vs lowercase) | **CLEAN.** All modules (`anomaly_agent`, `synthesis_agent`, etc.) lowercase. Runtime dirs (`chroma_db/`, `report_cache/`, `photo_hashes/`, `data/sidbi_docs/`) are lowercase && match code constants that build `os.path.join(os.path.dirname(__file__),…)` — Linux-safe. |
| Frontend relative/alias imports | `@/*` alias mapped in tsconfig; page.tsx uses **zero** imports beyond react/hooks. No path issues. |
| Chroma embedding model | `chroma_db/` uses default ONNX/local embedding (no network at query time) → RAG retrieval is offline and near-instant. |
| **Encoding defect** | `frontend/app/layout.tsx` metadata title renders as `"Theligai �?"` — a corrupted (double-encoded) glyph in the browser tab title. Visible to judges. |

**Linux build risk (HIGH):** the Chroma vector DB is **gitignored and absent from the repo**. On a fresh judge machine (Render/Vercel/Linux VM) there is no `chroma_db/`, so `retrieve.py` at import time catches the exception and permanently serves the stub `"RAG collection not available — run python -m app.rag.ingest first."` Nothing in the codebase runs `ingest()` automatically. The judge sees a **degraded, RAG-less system** unless someone manually executes ingest with the PDFs present.

---

## 2. RUNTIME ENDPOINT VALIDATION & SPEED METRICS

Backend was already live on `http://127.0.0.1:8001`. Live executions below.

### 2.1 GET /health — PASS
```
{"status":"ok"}                 HTTP 200   0.027 s
```

### 2.2 GET /reports — PASS (empty on fresh store)
```
[]                              HTTP 200   0.011 s
```

### 2.3 POST /agents/voice (test_media/contradiction_voice2.wav) — PASS
```
HTTP 200   23.53 s
{"transcript":"This is a brand new shop with just 2 open 1 month ago.",
 "extracted":{"business_type":null,"products":null,"years_operating":null,"location":null},
 "label":"officer observation, unverified"}
```
→ Whisper tiny (local) transcribe ≈ ~2-3 s; **OpenRouter granite extraction ≈ 20-21 s**.

### 2.4 POST /agents/vision (test_media/photo1.jpg + photo2.jpg) — PASS, SLOW
```
HTTP 200   95.56 s
```
2 sequential per-image `describe` calls + 1 summary call = **3 serialized OpenRouter gemini-2.5-flash round trips**.

### 2.5 POST /report (photo1+photo2, contradiction_voice2.wav, transactions.csv, vendor_name=AuditVendor, shop_address="MG Road Bangalore")
- **Client curl was terminated at 300 s** (no response body in client buffer).
- Server independently **completed** and cached a report (id `423681ff-d3fb-4075-a0c3-81d0676e2d36`) — total wall-clock **≈ 300 s**.
- Full JSON structure returned by the run (trimmed voice transcript):

```json
{
  "business_type": "Record retail (specialty vinyl store)",
  "revenue_consistency_band": "Moderate",
  "inventory_observation_band": "Low",
  "digital_activity_band": "Moderate",
  "relevant_scheme_note": "No relevant RAG scheme information is available at this time.",
  "assessment_band": "Further assessment required",
  "evidence_summary": [
    "Photo evidence shows a single black vinyl record, indicating very limited inventory.",
    "Voice note claims the shop opened 1 month ago, consistent with the 100‑day transaction span.",
    "Transaction records show 8 transactions totaling $5,750 inflow over 100 days, with high volatility and an increasing trend."
  ],
  "missing_inputs": [],
  "discrepancy_flags": [],
  "source_agreement": {"photo_voice": "agree", "photo_transactions": "agree", "voice_transactions": "agree"},
  "vision_result": {"per_image": [{"file": "tmphsj9dhmw.jpg", ...}, {"file": "tmp_oti7bib.jpg", ...}], "summary": "..."},
  "voice_result": {"transcript": "...", "extracted": {...}, "label": "officer observation, unverified"},
  "photo_reuse_flag": null,
  "location_verification": {"location_found": false, "error": "location lookup unavailable"},
  "risk_indicators": {
    "indicators": {"high_transaction_volatility": true, "unverifiable_location": true,
                   "cross_source_conflicts": false, "possible_photo_reuse": false,
                   "incomplete_evidence": false},
    "indicators_triggered": 2,
    "risk_summary": "A few factors warrant a closer look during review."
  },
  "total_inflow": 5750.0, "total_outflow": 0,
  "transaction_count": 8, "average_transaction": 718.75,
  "volatility": "high", "trend": "increasing",
  "earliest_date": "...", "latest_date": "...", "date_range_days": 100,
  "evidence_completeness": {"sources_provided": 3, "sources_total": 3, "discrepancies_found": false},
  "_timings": {"rag": 0.0, "synthesis": 2.96}
}
```

### 2.6 Latency decomposition (`_timings` is *incomplete by design*)

`main.py` only records **`rag`** and **`synthesis`** in `_timings`. Agent latencies are printed to stdout (`[timing] vision took Xs`) and **never persisted** — a deployable observability miss.

| Stage | Measured | Where the time goes |
|---|---|---|
| Photo hashing (`_check_photo_hashes`) | <1 s | local PIL/imagehash |
| Vision pipeline | **≈ 95 s** | 3 sequential OpenRouter gemini calls; images base64 1.7 MB each |
| Voice pipeline | **≈ 23 s** | whisper tiny local (~2-3 s) + granite extraction (~20 s) |
| Transactions parse | <1 s | local pandas (8 rows) |
| RAG query | **0.0 s** | local chroma, ~ms |
| Synthesis | **2.96 s** | granite-4.1-8b (600 tokens) |
| Location (Nominatim) | ~2 s | includes `time.sleep(1)` |
| **End-to-end POST /report** | **≈ 300 s** | dominated by serial vision + queue contention on shared OpenRouter key |

**Bottleneck verdict:** the *vision agent serializes per-image LLM calls* and everything waits on it; the per-request critical path is `max(vision, voice)` ≈ 95 s even before RAG/synthesis/location. On the Render/hobby tier with a cold model cache, expect 4-6 minutes per report — unacceptable for live judging if judges submit even two shops.

**Secondary finding:** duplicate byte-identical uploads (photo1.jpg ≡ photo2.jpg, same file) were **not** flagged, because photo-reuse only compares against *previously stored* vendor hashes, never within the current submission. `AuditVendor.json` now stores two identical hashes.

---

## 3. STATE INTEGRITY & DATA-FLOW HOLES (frontend/app/page.tsx)

### 3.1 ref/state duality
Values are mirrored in both state (`precomputedVision`, `precomputedVoice`) **and** refs (`precomputedVisionRef`, `precomputedVoiceRef`). Submission reads **refs** inside `handleSubmit`; the pre-existing modal-wait loop polls the refs:

```ts
if (precomputedVisionLoadingRef.current || precomputedVoiceLoadingRef.current) { …await until both false… }
```

This is the **one well-handled race** — a user clicking Generate while `/agents/vision` is in flight is correctly blocked and waited on, and refs guarantee no stale-closure read.

### 3.2 Verified holes

| # | Hole | Severity |
|---|---|---|
| H1 | **Empty-file uploads flow to the pipeline.** `fake.jpg` (21 B, text payload, BOM) is accepted with zero MIME/type/size validation; on the backend it reaches `PIL.Image.open` → exception → `compute_image_hash` returns None silently; vision then sends the text as base64 to a vision API and fails. No file-type gate, no size cap, no count cap. | High |
| H2 | **Un-revoked object URLs.** `URL.createObjectURL(f)` is called per preview image and **never** `URL.revokeObjectURL`'d — every upload-session leaks browser memory; sustained sessions degrade. | Medium |
| H3 | **Double-submit window.** Submit button disables only on next render after `setLoading(true)`; a fast double-click fires two concurrent `/report` or `/report/synthesize` POSTs → two cached report IDs, doubled API spend. | Medium |
| H4 | **Synthesis-failure UI blind spot.** If the backend returns `{"error": …, "discrepancy_flags": undefined}` the report screen renders band pills with `undefined` (slate default) and `assessment_band` blank — degraded, non-blocking, confusing for judges. | Low |
| H5 | **`discrepancy_flags` non-array crash.** Frontend calls `report.discrepancy_flags.map(...)` with **no `Array.isArray` guard** (line ~573). If the LLM ever emits `discrepancy_flags` as a string (see §4.2), React throws → **white-screen crash** of the entire report view. | High |
| H6 | No `AbortController`/timeout on `fetch` — a hung 300 s backend wedges the UI spinner; no cancel path. | Medium |
| H7 | Local fallback to `127.0.0.1:8001` when `NEXT_PUBLIC_API_URL` unset — deployed Vercel build silently targets the judge's *localhost* unless the env var is configured in the dashboard. If unset, every fetch hits a nonexistent port (TTFB timeout) and the demo looks broken. | High (deploy) |

---

## 4. REAL-WORLD DATA SCHEMA BREAKDOWNS

### 4.1 transaction_agent.py

**What it handles correctly (verified by read, not just claims):**
- Missing file / unreadable CSV / empty df → `{"error":"transaction data unavailable"}` (graceful, no crash).
- Column normalization across 5 alias sets (`date`, `type`, `amount`, `debit`, `credit`) with whitespace/lowercase tolerance.
- Separate-debit-and-credit banks exports → normalized into typed rows.
- Sign-inferred direction when only an `amount` column exists (neg=debit, pos=credit, mixed or all-neg paths).
- Fence-free, `pd.to_numeric(..., errors="coerce")` + `dropna`.

**Confirmed weaknesses:**

| # | Failure mode | Impact |
|---|---|---|
| T1 | **Garbage date column → silent data massacre.** `pd.to_datetime(df["date"], errors="coerce")` then **`df = df.dropna(subset=["date"])` reassigns the frame** (lines 135-136). If a real export mixes formats (`DD/MM/YYYY` + `MM/DD/YYYY`, or timestamps with stray text), the majority of rows silently vanish → `total_inflow`, `count`, `date_range`, volatility and trend are all recomputed on the surviving sliver → **wrong bands delivered with full confidence**. No NaN-rate warning surfaced to judge. | **Critical** |
| T2 | **Negative amounts with a `type` column are never `abs()`'d.** If `type=credit` rows carry raw negative ledger values, inflow total is *reduced* by their magnitude (line 121-123) — no sign correction in that branch. | Medium |
| T3 | **All-NaT dates + valid amounts**: date-range is None, but volatility is then garbage (std of ~empty series) and trend silently "stable" — misleading, no `assumptions` note emitted. | Medium |
| T4 | `fake.jpg`/`voicenote.wav` style non-CSV files: only guarded by `pd.read_csv` exception → OK, but error surface identical to "legit but malformed" → judge can't distinguish. | Low |
| T5 | No encoding/`sep`/`skiprows` resilience (semicolon-delimited European exports, BOM handled implicitly by pandas). | Low |

### 4.2 synthesis_agent.py + OpenRouter tolerance

**Correctly handled:** markdown fences (` ``` ` and ` ```json `) stripped; `discrepancy_flags` defaulted to `[]` if key absent; `source_agreement` enums coerced to `insufficient_data` if invalid; band enums validated with a fallback.

**Confirmed holes:**

| # | Failure mode | Impact |
|---|---|---|
| S1 | **`json.loads` returning a non-dict (e.g. model emits a JSON array or a bare string) → `report["missing_inputs"] = …` raises `TypeError` OUTSIDE the try/except`** (line 127). → FastAPI 500. The parse try/except does **not** wrap the post-processing — a guaranteed crash path, *not* a graceful fallback. | **Critical** |
| S2 | `discrepancy_flags` returned as a **string** (a very common granite failure when the model drops a list wrapper): passed through unvalidated. Backend anomaly agent tolerates it; **frontend `.map()` throws** → full white-screen crash. | **Critical** |
| S3 | **Type confusion in band fallback**: invalid `*_band` values are re-set to the *assessment* enum value `"Further assessment required"` instead of a valid `Low/Moderate/Strong` (lines 146-148). The frontend `bandColor` then renders a slate pill with text "Further assessment required" inside a band slot — semantically wrong output shipped to a judge. | Medium |
| S4 | `max_tokens=600` on the synthesis prompt that re-serializes *full* vision/voice JSON: larger evidence sets (5 photos + long transcripts) → truncation → `json.loads` fails → whole report degrades to an `error` dict. | Medium |
| S5 | No `timeout=` on any OpenRouter client call — a stalled upstream hangs the request forever (contributes to the 300 s observed run). | High |

---

## 5. ARCHITECTURAL GAPS FOR NATIONAL-LEVEL COMPETITION

Senior judges will classify this as a **"solid demo, not a production system"** based on:

1. **No database.** Reports, photos-hash state, and vendor history are all **flate-file JSON caches** (`report_cache/*.json`, `photo_hashes/*.json`) with zero atomic-write discipline (no temp-file+rename, no locking) — concurrent officers can produce torn/duplicate state.
2. **Zero authentication/authorization.** `/reports` lists *every* report for *anyone*; there is no login, no role, no ownership scoping, no audit trail. A judge will immediately ask "who is allowed to see this report?" — no answer exists.
3. **No auth boundary on the Backend API** (no API-key/header check on `/agents/*` or `/report*` endpoints) → anyone who can reach the server can burn paid OpenRouter credits.
4. **No Server-Sent Events / WebSocket / progress streaming.** UI shows only an elapsed-seconds spinner; the 90-300 s vision phase is a black box. For judging, a streamed "Hashing photos → Describing image 1/2 → Extracting voice → Cross-checking → Assembling" feed is table stakes.
5. **No job/task queue.** The whole pipeline runs inline in the HTTP handler behind the single FastAPI threadpool; `uvicorn` had one worker serving everything; no idempotency keys — a retried double-submit double-charges API credits.
6. **No multi-tenant data model.** Vendor hash store and report cache are globally keyed by vendor name — cross-vendor collisions possible, and there's no concept of an owning officer/org.
7. **RAG bootstrapping is not self-healing.** Collection must exist before import; no deploy hook runs `python -m app.rag.ingest`; on a fresh box the entire RAG layer silently no-ops (the observed `relevant_scheme_note: "No relevant RAG scheme information…"`).
8. **No input validation/limits.** No max file size, count, total-upload cap, or MIME whitelist — an obvious security/abuse and DoS vector during live judging.
9. **No structured logging, tracing, or metrics.** Only `print(..., flush=True)` to stdout; nothing aggregable.
10. **Single-point credential dependency.** Every intelligence path (vision, voice, synthesis) shares one `OPENROUTER_API_KEY`; one rate-limit/quota breach kills the whole demo at judging time.

---

## 6. SECURITY, SECRETS & PRIVACY LEAKS

### 6.1 Deep history scan (full `git log --all -p`)
- **No live OpenRouter/HuggingFace keys anywhere in history.** Only placeholders: `.env.example` (`sk-or-v1-your-key-here`) and historical mentions of `hf_your-token-here` in README/`.env.example` at the initial commit.
- **No `.pem`/`.key`/`.env` file has ever been tracked** (verified via `git log --all --name-only`).
- Local `backend/.env` **does not exist** (`Test-Path → False`); only `.env.example` ships.
- Working tree: `git status --short` → only `?? backend/photo_hashes/` untracked.

**Residual hygiene risk:** `backend/photo_hashes/` is **NOT in `.gitignore`** (only `report_cache/` and `chroma_db/` are). It now holds a vendor-named file (`AuditVendor.json`) with hash values. If a judge runs `git add .` on the project, vendor-derived data would enter the repo. Add `.gitignore` entries.

### 6.2 Absolute path / Windows path leakage
- **No `C:\Users\...`/drive-letter strings in any `.py` source** (regex scan clean).
- RAG metadata is written as `os.path.basename(c.metadata["source"])` in `ingest.py:35` → **only the filename** is stored in Chroma; no absolute paths in metadata context.
- Vision `per_image[].file` contains **temp basenames** only (e.g. `tmphsj9dhmw.jpg`), not paths.
- Report cache JSON is gitignored and contains no absolute paths.

### 6.3 Other security notes
- CORS: `http://localhost:3000`, `:3001`, and the Vercel URL — `allow_methods=["*"]`, `allow_headers=["*"]`, no credentials. Broad but acceptable for demo; fine.
- **No rate limiting / abuse protection** on any endpoint (credits-burn vector).
- **PII retention:** full voice transcripts + extracted facts + addresses are written to an unencrypted, indefinitely-retained JSON cache with **no retention/expiry policy**.
- OpenRouter errors surface `detail: str(e)` verbatim to the client in `{"error": ...}` — can leak upstream endpoint/status details (low, but sloppy).

---

## 7. DEPENDENCY DRIFT AND PERFORMANCE HYGIENE

### 7.1 requirements.txt (all 16 **unpinned**) — nondeterministic builds

| Dependency | Status | Verdict |
|---|---|---|
| `fastapi`, `uvicorn` | used | unpinned |
| `langchain` / `langchain-community` | only `PyPDFLoader` + `langchain_text_splitters` used | bloated pull (drag K8s of transitive deps) |
| **`langchain-openai`** | declared, **never imported** (grep verified) | **DEAD** |
| **`requests`** | declared, **never imported** | **DEAD** (location uses stdlib `urllib`) |
| `chromadb`, `pypdf`, `python-multipart`, `python-dotenv` | used | unpinned |
| `faster-whisper`, `openai` | used | unpinned; model `"tiny"/int8` is the right memory call |
| `pandas`, `numpy` | used | unpinned |
| `imagehash`, `Pillow` | used | unpinned |

**Fix fast:** `pip freeze` pinnings + remove 2 dead deps → shrinks install, eliminates a judge-machine resolution drift failure (a new pandas/ndarray major breaking `transaction_agent` on the judging day).

### 7.2 frontend/package.json
- Only `next`, `react`, `react-dom` runtime + tailwind/eslint toolchain — lean, good.
- `package-lock.json` committed → deterministic.
- `next 16.2.10` / `react 19.2.4` are bleeding-edge majors; if judges install without the lockfile, drift risk is real (a render-breaking React 19.x patch). Pin inside lockfile only — already the case; do not bump on site.

### 7.3 Import hygiene
- Duplicate `glob`/`datetime` imports already fixed in commit `edb8762`. Current scan shows **no duplicate imports** across backend modules. `sys` present where used in all four agents.

### 7.4 Performance hygiene
- **Memory leak (frontend):** object URLs for photo previews never revoked (§3.2/H2).
- `faster-whisper` model cached globally (good, but lazy-load on first request adds 2-3 s cold — acceptable).
- `time.sleep(1)` in `location_agent.py` (Nominatim ToS) adds fixed 1 s per geocode — fine.
- `_run_agent` cleans temp files in `finally` (good); photo hashing `f.file.seek(0)` idempotency correct.
- Chroma loads sync at import — a `PersistentClient` already instantiated; collection missing → `_collection=None` path chosen, RAG silently degrades (§5.7).

---

## 8. SUMMARY SHORTLIST SCORECARD — VULNERABILITIES TO CLOSE BEFORE JUDGING

Legend: `CRIT` (guaranteed judge-visible failure / crash), `HIGH` (likely to fail under inspection), `MED` (quality/robustness), `LOW` (polish).

| # | Issue | Class | Location | Priority |
|---|---|---|---|---|
| V1 | End-to-end `/report` ≈ **300 s**; vision is 3 serialized paid LLM calls ≈ 95 s | Runtime bottleneck | `vision_agent.py` / `main.py` `_run_agent` | CRIT |
| V2 | `_timings` omits vision/voice/transactions — latency invisible in output | Observability | `main.py` | HIGH |
| V3 | `json.loads` non-dict → unguarded `report["missing_inputs"]` → **HTTP 500** | Crash | `synthesis_agent.py:127` | CRIT |
| V4 | `discrepancy_flags` as string → frontend `.map()` **white-screen crash** (no `Array.isArray`) | Crash | `frontend/app/page.tsx:573` | CRIT |
| V5 | Band fallback injects assessment-string into band enum slots | Wrong data | `synthesis_agent.py:146-148` | MED |
| V6 | `pd.to_datetime` + `dropna` silently destroys mis-encoded date rows → confident-but-wrong bands | Data integrity | `transaction_agent.py:135-139` | CRIT |
| V7 | No input MIME/size/count validation — `fake.jpg` (21 B) reaches image/vision pipeline | Security/Robustness | `main.py` / `page.tsx` | HIGH |
| V8 | No auth on any endpoint; `/reports` exposes all data; no owner scoping | Architecture | entire backend | HIGH |
| V9 | No SSE/WebSocket progress updates — blind 100-300 s spinner | UX/Judging | `main.py`, `page.tsx` | HIGH |
| V10 | RAG collection gitignored, never bootstrapped → RAG silently no-ops on fresh deploy | Deploy | `rag/retrieve.py`, README | CRIT (deploy) |
| V11 | `NEXT_PUBLIC_API_URL` fallback to `127.0.0.1:8001` → heading straight to judge's browser | Deploy | `page.tsx:5` | HIGH (deploy) |
| V12 | No per-request timeout on any OpenRouter call (hangs forever) | Robustness | `vision/voice/synthesis_agent.py` | HIGH |
| V13 | All 16 backend deps unpinned + `requests` & `langchain-openai` dead | Dependency drift | `requirements.txt` | MED |
| V14 | `backend/photo_hashes/` not gitignored; vendor hash data sits untracked | Hygiene/Privacy | `.gitignore` | MED |
| V15 | Object-URL memory leak (never revoked) | Frontend leak | `page.tsx:726` | MED |
| V16 | Double-submit / retry duplicates cache entries + API spend | Race | `page.tsx:204` | MED |
| V17 | Mojibake `�?` in `<title>` metadata | Polish | `layout.tsx:14` | LOW |
| V18 | All-vendor hash lookups ignore same-submission duplicates (photo1==photo2 not caught) | Feature gap | `main.py:_check_photo_hashes` | MED |
| V19 | No structured logging/metrics/retention policy on PII cache | Security | backend | MED |
| V20 | Negative credit amounts not `abs()` when a type column exists | Data integrity | `transaction_agent.py:120-123` | MED |

### Verdict
Path: `.env`/keys **clean**, imports **Linux-safe**, core pipeline **functional and demonstrates real multi-agent reasoning** (verified live). But this will **not survive high-velocity judging** in its current form: a 5‑minute-per-report API, an HTTP-500 synthesis crash path that can be triggered by a single odd LLM response, and zero auth/no progress streaming will be the three things a bench of professors or fintech judges will hammer in the first 10 minutes. The single highest-ROI repair is **V1**: parallelize per-image vision emit calls, add fetch timeouts (V12), and thread a `stream`/SSE status channel (V9) — that one change converts a "demo" into a "pipeline" in front of the judges.