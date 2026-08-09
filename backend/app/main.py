import asyncio
import functools
import glob
import json
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime
from io import BytesIO
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

OFFICER_PIN = os.getenv("OFFICER_PIN")


def verify_officer_pin(x_officer_pin: str | None = Header(None)):
    if not OFFICER_PIN:
        return
    if x_officer_pin != OFFICER_PIN:
        raise HTTPException(status_code=401, detail="Invalid officer PIN")

from app.rag.retrieve import retrieve
from app.agents.vision_agent import analyze_photos
from app.agents.voice_agent import process_voice, process_manual_text
from app.agents.transaction_agent import analyze_transactions
from app.agents.synthesis_agent import synthesize_report
from app.agents.location_agent import verify_location, check_address_consistency
from app.agents.anomaly_agent import compute_risk_indicators, compute_profile_completeness, compute_cross_verification
from app.agents.document_agent import process_documents

app = FastAPI(title="HackVerse RAG API")

REPORT_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "report_cache")
PHOTO_HASH_DIR = os.path.join(os.path.dirname(__file__), "..", "photo_hashes")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://hack-verse-psi.vercel.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str


_DOC_TYPE_ALIASES = {
    "gst_certificate": ["gst", "goods services tax", "gstin"],
    "udyam_certificate": ["udyam", "msme", "udyog"],
    "bank_statement": ["bank", "statement", "passbook", "account"],
    "aadhaar_card": ["aadhaar", "aadhar", "uidai"],
    "rent_agreement": ["rent", "agreement", "lease", "tenancy"],
    "trade_license": ["trade", "license", "licence", "shops establishment"],
}


def _infer_document_type(filename: str) -> str | None:
    lower = filename.lower().replace("_", "").replace("-", "").replace(" ", "")
    for doc_type, aliases in _DOC_TYPE_ALIASES.items():
        if any(alias in lower for alias in aliases):
            return doc_type
    return None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/reports")
def list_reports():
    files = sorted(
        glob.glob(os.path.join(REPORT_CACHE_DIR, "*.json")),
        key=os.path.getmtime,
        reverse=True,
    )
    entries = []
    for fpath in files:
        try:
            with open(fpath) as f:
                data = json.load(f)
            mtime = os.path.getmtime(fpath)
            entries.append({
                "report_id": data.get("report_id"),
                "business_type": data.get("business_type"),
                "assessment_band": data.get("assessment_band"),
                "generated_at": datetime.fromtimestamp(mtime).isoformat(),
            })
        except Exception:
            continue
    return entries


@app.get("/vendors/{vendor_name}/history")
def vendor_history(vendor_name: str):
    vendor = vendor_name.lower()
    entries = []
    for path in glob.glob(os.path.join(REPORT_CACHE_DIR, "*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            continue
        if data.get("vendor_name", "").lower() != vendor:
            continue
        mtime = os.path.getmtime(path)
        entries.append({
            "report_id": data["report_id"],
            "generated_at": datetime.fromtimestamp(mtime).isoformat(),
            "assessment_band": data.get("assessment_band", ""),
            "revenue_consistency_band": data.get("revenue_consistency_band", ""),
            "inventory_observation_band": data.get("inventory_observation_band", ""),
            "digital_activity_band": data.get("digital_activity_band", ""),
        })
    entries.sort(key=lambda e: e["generated_at"])
    return entries


@app.get("/reports/{report_id}")
def get_report(report_id: str):
    cache_path = os.path.join(REPORT_CACHE_DIR, f"{report_id}.json")
    if not os.path.isfile(cache_path):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "report not found"})
    with open(cache_path) as f:
        return json.load(f)


@app.post("/rag/query")
def rag_query(req: QueryRequest):
    results = retrieve(req.query, k=3)
    return {"query": req.query, "results": results}


@app.post("/agents/vision")
async def agents_vision(files: List[UploadFile] = File(...)):
    temp_paths = []
    try:
        for f in files:
            suffix = os.path.splitext(f.filename)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(f.file, tmp)
                temp_paths.append(tmp.name)
        return await analyze_photos(temp_paths)
    finally:
        for p in temp_paths:
            os.remove(p)


@app.post("/agents/voice")
async def agents_voice(file: UploadFile = File(...), language: str = Form(None)):
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = tmp.name
    try:
        return process_voice(temp_path, language=language or None)
    finally:
        os.remove(temp_path)


async def _run_agent(
    label: str,
    files_data: list | None,
    single_file: bool,
    handler,
):
    if files_data is None:
        return None
    t0 = time.time()
    paths = []
    try:
        if single_file:
            f = files_data
            suffix = os.path.splitext(f.filename)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(f.file, tmp)
                path = tmp.name
            if asyncio.iscoroutinefunction(handler):
                result = await handler(path)
            else:
                result = await asyncio.to_thread(handler, path)
            paths.append(path)
        else:
            for f in files_data:
                suffix = os.path.splitext(f.filename)[1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    shutil.copyfileobj(f.file, tmp)
                    paths.append(tmp.name)
            if asyncio.iscoroutinefunction(handler):
                result = await handler(paths)
            else:
                result = await asyncio.to_thread(handler, paths)
        return result
    finally:
        for p in paths:
            os.remove(p)
        elapsed = round(time.time() - t0, 2)
        print(f"[timing] {label} took {elapsed}s", flush=True)


async def _check_photo_hashes(photo_files: list[UploadFile], vendor_name: str) -> str | None:
    if not vendor_name:
        return None
    try:
        from imagehash import average_hash, hex_to_hash
        from PIL import Image
    except ImportError:
        return None
    try:
        new_hashes = []
        for f in photo_files:
            content = await f.read()
            img = Image.open(BytesIO(content))
            h = str(average_hash(img))
            new_hashes.append(h)
            f.file.seek(0)

        vendor_file = os.path.join(PHOTO_HASH_DIR, f"{vendor_name}.json")
        existing = []
        if os.path.isfile(vendor_file):
            with open(vendor_file) as fh:
                existing = json.load(fh)

        for h in new_hashes:
            h_obj = hex_to_hash(h)
            for eh in existing:
                if h_obj - hex_to_hash(eh) <= 2:
                    os.makedirs(PHOTO_HASH_DIR, exist_ok=True)
                    all_hashes = existing + new_hashes
                    with open(vendor_file, "w") as fh:
                        json.dump(all_hashes, fh)
                    return "This photo appears visually identical to one submitted in a previous assessment for this vendor \u2014 please verify it was taken during this visit."

        os.makedirs(PHOTO_HASH_DIR, exist_ok=True)
        all_hashes = existing + new_hashes
        with open(vendor_file, "w") as fh:
            json.dump(all_hashes, fh)
        return None
    except Exception:
        return None


@app.post("/report/synthesize", dependencies=[Depends(verify_officer_pin)])
async def report_synthesize(
    vision_result: str = Form(None),
    voice_result: str = Form(None),
    manual_voice_text: str = Form(None),
    voice_language: str = Form(None),
    pin_lat: float = Form(None),
    pin_lon: float = Form(None),
    transactions: Optional[UploadFile] = File(None),
    voice: Optional[UploadFile] = File(None),
    documents: Optional[List[UploadFile]] = File(None),
    vendor_name: str = Form(None),
    shop_address: str = Form(None),
    has_savings_account: str = Form(None),
    annual_turnover: float = Form(None),
    udyam_number: str = Form(None),
):
    timings = {}
    
    vision_data = json.loads(vision_result) if vision_result else None
    voice_data = json.loads(voice_result) if voice_result else None

    if manual_voice_text and manual_voice_text.strip() and (
        voice_data is None or voice_data.get("transcription_failed")
    ):
        voice_data = await asyncio.to_thread(process_manual_text, manual_voice_text)
    
    transaction_result = None
    if transactions is not None:
        transaction_result = await _run_agent("transactions", transactions, True, analyze_transactions)

    doc_paths = {
        "gst_certificate": None,
        "udyam_certificate": None,
        "bank_statement": None,
        "aadhaar_card": None,
        "rent_agreement": None,
        "trade_license": None,
    }
    document_result = None
    try:
        doc_files = documents or []
        if doc_files:
            for upload in doc_files:
                inferred_type = _infer_document_type(upload.filename or "")
                if inferred_type is None:
                    continue
                suffix = os.path.splitext(upload.filename)[1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    shutil.copyfileobj(upload.file, tmp)
                    doc_paths[inferred_type] = tmp.name
            document_result = process_documents(doc_paths)
    except Exception as e:
        document_result = {
            "documents_processed": [],
            "documents_missing": list(doc_paths.keys()),
            "extracted": {},
            "verification_signals": {},
            "error": f"Document processing failed: {str(e)}",
        }
    finally:
        for p in doc_paths.values():
            if p and os.path.isfile(p):
                os.remove(p)

    t0 = time.time()
    rag_context = retrieve("MSME working capital lending guidance", k=2)
    timings["rag"] = round(time.time() - t0, 2)

    t0 = time.time()
    report_data = synthesize_report(
        vision_data, voice_data, transaction_result, rag_context,
        document_result=document_result,
    )
    timings["synthesis"] = round(time.time() - t0, 2)
    
    report_data["vision_result"] = vision_data
    report_data["voice_result"] = voice_data
    report_data["document_analysis"] = _sanitize_document_analysis(document_result)
    if vendor_name:
        report_data["vendor_name"] = vendor_name
    if has_savings_account:
        report_data["has_savings_account"] = has_savings_account
    if annual_turnover:
        report_data["annual_turnover"] = annual_turnover
    if udyam_number:
        report_data["udyam_number"] = udyam_number
    report_data["photo_reuse_flag"] = None

    if shop_address:
        location_result = await asyncio.to_thread(verify_location, vendor_name or "", shop_address, pin_lat, pin_lon)
        report_data["location_verification"] = location_result
        if location_result.get("location_found") and voice_data:
            voice_location = voice_data.get("extracted", {}).get("location", "")
            if voice_location:
                flag = check_address_consistency(voice_location, location_result)
                if flag:
                    if "discrepancy_flags" not in report_data:
                        report_data["discrepancy_flags"] = []
                    report_data["discrepancy_flags"].append(flag)

    report_data["risk_indicators"] = compute_risk_indicators(
        vision_data, voice_data, transaction_result,
        report_data.get("discrepancy_flags"),
        report_data.get("location_verification"),
        report_data.get("photo_reuse_flag"),
    )

    if document_result:
        extra_flags = compute_cross_verification(
            vision_data, voice_data, transaction_result, document_result
        )
        if extra_flags:
            if "discrepancy_flags" not in report_data:
                report_data["discrepancy_flags"] = []
            report_data["discrepancy_flags"].extend(extra_flags)

    report_data["document_analysis"] = _sanitize_document_analysis(document_result)

    return _finalize_report(report_data, transaction_result, rag_context, timings)


@app.post("/report", dependencies=[Depends(verify_officer_pin)])
async def report(
    photos: Optional[List[UploadFile]] = File(None),
    voice: Optional[UploadFile] = File(None),
    transactions: Optional[UploadFile] = File(None),
    documents: Optional[List[UploadFile]] = File(None),
    manual_voice_text: str = Form(None),
    voice_language: str = Form(None),
    pin_lat: float = Form(None),
    pin_lon: float = Form(None),
    vendor_name: str = Form(None),
    shop_address: str = Form(None),
    has_savings_account: str = Form(None),
    annual_turnover: float = Form(None),
    udyam_number: str = Form(None),
):
    timings = {}
    photo_reuse_flag = await _check_photo_hashes(photos, vendor_name) if photos else None

    doc_paths = {
        "gst_certificate": None,
        "udyam_certificate": None,
        "bank_statement": None,
        "aadhaar_card": None,
        "rent_agreement": None,
        "trade_license": None,
    }
    document_result = None
    try:
        doc_files = documents or []
        if doc_files:
            for upload in doc_files:
                inferred_type = _infer_document_type(upload.filename or "")
                if inferred_type is None:
                    continue
                suffix = os.path.splitext(upload.filename)[1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    shutil.copyfileobj(upload.file, tmp)
                    doc_paths[inferred_type] = tmp.name
            document_result = process_documents(doc_paths)
    except Exception as e:
        document_result = {
            "documents_processed": [],
            "documents_missing": list(doc_paths.keys()),
            "extracted": {},
            "verification_signals": {},
            "error": f"Document processing failed: {str(e)}",
        }
    finally:
        for p in doc_paths.values():
            if p and os.path.isfile(p):
                os.remove(p)

    coros = []
    mapping = []
    if photos is not None:
        coros.append(_run_agent("vision", photos, False, analyze_photos))
        mapping.append("vision")
    if voice is not None or not (manual_voice_text or "").strip():
        voice_handler = functools.partial(process_voice, language=voice_language or None) if voice_language else process_voice
        coros.append(_run_agent("voice", voice, True, voice_handler))
        mapping.append("voice")
    if transactions is not None:
        coros.append(_run_agent("transactions", transactions, True, analyze_transactions))
        mapping.append("transactions")

    gathered = await asyncio.gather(*coros) if coros else []

    vision_result = None
    voice_result = None
    transaction_result = None
    for label, result in zip(mapping, gathered):
        if label == "vision":
            vision_result = result
        elif label == "voice":
            voice_result = result
        elif label == "transactions":
            transaction_result = result

    if manual_voice_text and manual_voice_text.strip() and (
        voice_result is None or voice_result.get("transcription_failed")
    ):
        voice_result = await asyncio.to_thread(process_manual_text, manual_voice_text)

    t0 = time.time()
    rag_context = retrieve("MSME working capital lending guidance", k=2)
    timings["rag"] = round(time.time() - t0, 2)

    t0 = time.time()
    report_data = synthesize_report(
        vision_result, voice_result, transaction_result, rag_context,
        document_result=document_result,
    )
    timings["synthesis"] = round(time.time() - t0, 2)
    
    report_data["vision_result"] = vision_result
    report_data["voice_result"] = voice_result
    report_data["document_analysis"] = _sanitize_document_analysis(document_result)
    if vendor_name:
        report_data["vendor_name"] = vendor_name
    if has_savings_account:
        report_data["has_savings_account"] = has_savings_account
    if annual_turnover:
        report_data["annual_turnover"] = annual_turnover
    if udyam_number:
        report_data["udyam_number"] = udyam_number
    report_data["photo_reuse_flag"] = photo_reuse_flag

    if shop_address:
        location_result = await asyncio.to_thread(verify_location, vendor_name or "", shop_address, pin_lat, pin_lon)
        report_data["location_verification"] = location_result
        if location_result.get("location_found") and voice_result:
            voice_location = voice_result.get("extracted", {}).get("location", "")
            if voice_location:
                flag = check_address_consistency(voice_location, location_result)
                if flag:
                    if "discrepancy_flags" not in report_data:
                        report_data["discrepancy_flags"] = []
                    report_data["discrepancy_flags"].append(flag)

    report_data["risk_indicators"] = compute_risk_indicators(
        vision_result, voice_result, transaction_result,
        report_data.get("discrepancy_flags"),
        report_data.get("location_verification"),
        report_data.get("photo_reuse_flag"),
    )

    if document_result:
        extra_flags = compute_cross_verification(
            vision_result, voice_result, transaction_result, document_result
        )
        if extra_flags:
            if "discrepancy_flags" not in report_data:
                report_data["discrepancy_flags"] = []
            report_data["discrepancy_flags"].extend(extra_flags)

    report_data["document_analysis"] = _sanitize_document_analysis(document_result)

    return _finalize_report(report_data, transaction_result, rag_context, timings)


def _sanitize_document_analysis(document_result: dict | None) -> dict | None:
    if not document_result:
        return None
    sanitized = {
        "documents_processed": document_result.get("documents_processed", []),
        "documents_missing": document_result.get("documents_missing", []),
        "verification_signals": document_result.get("verification_signals", {}),
        "extracted": {},
    }
    for doc_type, info in document_result.get("extracted", {}).items():
        if isinstance(info, dict):
            sanitized["extracted"][doc_type] = {
                "document_type": info.get("document_type"),
                "key_fields": info.get("key_fields", {}),
                "verified": info.get("verified", False),
                "verification_reason": info.get("verification_reason", ""),
            }
        else:
            sanitized["extracted"][doc_type] = info
    return sanitized


def _finalize_report(report_data, transaction_result, rag_context, timings):
    input_errors = []
    missing = []
    
    if report_data.get("vision_result") is None: missing.append("photos")
    if report_data.get("voice_result") is None: missing.append("voice")
    if transaction_result is None: missing.append("transactions")

    document_analysis = report_data.get("document_analysis")
    if document_analysis:
        doc_processed = document_analysis.get("documents_processed", [])
        if not doc_processed:
            missing.append("documents")
    else:
        missing.append("documents")

    vision_result = report_data.get("vision_result")
    voice_result = report_data.get("voice_result")
    if vision_result and "error" in vision_result:
        input_errors.append(f"Shop photos: {vision_result['error']} — please upload a clearer photo")
    if voice_result and "error" in voice_result:
        input_errors.append(f"Voice note: {voice_result['error']} — please re-record the note or type field notes instead")
    if transaction_result and "error" in transaction_result:
        input_errors.append(f"Transaction data: {transaction_result['error']} — please provide a valid CSV export")
    if "error" in report_data:
        input_errors.append("synthesis: " + report_data["error"])

    report_data["missing_inputs"] = missing
    report_data["input_errors"] = input_errors
    report_data["_timings"] = timings

    sources_provided = 0
    if report_data.get("vision_result") is not None:
        sources_provided += 1
    if report_data.get("voice_result") is not None:
        sources_provided += 1
    if transaction_result is not None and "error" not in transaction_result:
        sources_provided += 1
    if document_analysis and document_analysis.get("documents_processed"):
        sources_provided += 1
    report_data["evidence_completeness"] = {
        "sources_provided": sources_provided,
        "sources_total": 4,
        "discrepancies_found": bool(report_data.get("discrepancy_flags")),
    }

    if transaction_result and "error" not in transaction_result:
        TXN_FIELDS = ["total_inflow", "total_outflow", "transaction_count", "average_transaction", "volatility", "trend", "date_range_days", "earliest_date", "latest_date", "format_notes"]
        for f in TXN_FIELDS:
            if f in transaction_result:
                report_data[f] = transaction_result[f]

    # Formal status fields (from upload screen)
    has_savings_account = report_data.get("has_savings_account")
    annual_turnover = report_data.get("annual_turnover")
    udyam_number = report_data.get("udyam_number")
    vendor_formal_status = None
    if has_savings_account is not None:
        vendor_formal_status = {
            "has_savings_account": has_savings_account,
            "annual_turnover": annual_turnover,
            "udyam_number": udyam_number,
            "gst_required": annual_turnover >= 2000000 if annual_turnover else None,
        }
        report_data["vendor_formal_status"] = vendor_formal_status
        if has_savings_account == "No" and not report_data.get("onboarding_pathway"):
            report_data["onboarding_pathway"] = [
                "Open a Jan Dhan Yojana zero-balance savings account at any nationalized bank — required for loan disbursement, takes 30 minutes with Aadhaar card"
            ]
        elif has_savings_account == "No" and report_data.get("onboarding_pathway"):
            if not any("Jan Dhan Yojana" in step for step in report_data["onboarding_pathway"]):
                report_data["onboarding_pathway"] = [
                    "Open a Jan Dhan Yojana zero-balance savings account at any nationalized bank — required for loan disbursement, takes 30 minutes with Aadhaar card"
                ] + report_data["onboarding_pathway"]

    location_verification = report_data.get("location_verification")
    try:
        completeness = compute_profile_completeness(
            vision_result, voice_result, transaction_result,
            document_analysis, vendor_formal_status,
            location_verification=location_verification,
            discrepancy_flags=report_data.get("discrepancy_flags", []),
        )
        report_data["profile_completeness"] = completeness
    except Exception:
        report_data["profile_completeness"] = {
            "completeness_score": 0,
            "completeness_tier": "Minimal",
            "missing_for_next_tier": [],
            "label": "Profile Completeness Index — reflects evidence gathered, not creditworthiness",
        }

    seen = set()
    sources_cited = []
    for r in rag_context:
        src = r.get("source", "")
        if src and src not in seen:
            seen.add(src)
            sources_cited.append(src)
    report_data["sources_cited"] = sources_cited

    report_id = str(uuid.uuid4())
    os.makedirs(REPORT_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(REPORT_CACHE_DIR, f"{report_id}.json")
    report_data["report_id"] = report_id
    try:
        with open(cache_path, "w") as f:
            json.dump(report_data, f)
    except Exception:
        pass

    return report_data