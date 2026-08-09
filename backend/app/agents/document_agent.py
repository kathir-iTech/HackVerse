import json
import os
import re
import sys

from dotenv import load_dotenv
from openai import OpenAI
from app.utils.privacy import scrub_pii

load_dotenv()

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    print("ERROR: OPENROUTER_API_KEY environment variable is not set.", file=sys.stderr)
    api_key = ""

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)
VISION_MODEL = "google/gemini-2.5-flash"

_DOC_TYPE_HINTS = {
    "gst_certificate": "GST Certificate",
    "udyam_certificate": "Udyam/MSME Certificate",
    "bank_statement": "Bank Statement",
    "aadhaar_card": "Aadhaar Card",
    "rent_agreement": "Rent Agreement",
    "trade_license": "Trade License",
}

_GSTIN_PATTERN = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9][Z][A-Z0-9]$')
_UDYAM_PATTERN = re.compile(r'^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$')
_BANK_DATE_PATTERN = re.compile(r'\b(?:\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})\b')
_BANK_AMOUNT_PATTERN = re.compile(r'(?:INR\s*|₹\s*)?[\d,]+(?:\.\d{1,2})?')
_LICENSE_PATTERN = re.compile(r'[A-Z0-9/\-]{5,20}')


def _char_to_val(ch: str) -> int:
    if ch.isdigit():
        return int(ch)
    return ord(ch.upper()) - ord("A") + 10


def _val_to_char(val: int) -> str:
    if val < 10:
        return str(val)
    return chr(ord("A") + val - 10)


def _gstin_checksum(gstin_14: str) -> str | None:
    if len(gstin_14) != 14:
        return None
    total = 0
    for i, ch in enumerate(gstin_14, start=1):
        try:
            val = _char_to_val(ch)
        except (ValueError, TypeError):
            return None
        total += val * i
    remainder = total % 36
    return _val_to_char(remainder)


def _validate_gstin_checksum(reg_number: str) -> tuple[bool, str | None]:
    reg_number = str(reg_number).strip().upper()
    if not _GSTIN_PATTERN.match(reg_number):
        return False, f"GSTIN format invalid: {reg_number}"
    gstin_14 = reg_number[:14]
    expected_check_char = reg_number[14]
    computed_check = _gstin_checksum(gstin_14)
    if computed_check is None:
        return False, f"GSTIN checksum calculation failed for: {reg_number}"
    if computed_check != expected_check_char:
        return False, f"GSTIN checksum mismatch for {reg_number}: expected {expected_check_char}, computed {computed_check}"
    return True, None

_VISION_STRICT_JSON_PROMPT = (
    "You are a document data extraction engine. Extract ONLY the fields listed below from this document image. "
    "Return ONLY a strict JSON object — no markdown, no prose, no explanations. "
    "If a field is not visible, set it to null. Do not guess or fabricate values.\n\n"
    "Required JSON keys:\n"
    '  "document_type": string (one of: "GST Certificate", "Udyam/MSME Certificate", "Bank Statement", '
    '"Aadhaar Card", "Rent Agreement", "Trade License")\n'
    '  "extracted_id": string (the registration/license/ID number exactly as shown, or null)\n'
    '  "business_name": string (name of business or person as shown, or null)\n'
    '  "issue_date": string (issue/validity date as shown, or null)\n\n'
    "Example output:\n"
    '{"document_type": "GST Certificate", "extracted_id": "27AAAAA0000A1Z5", '
    '"business_name": "Acme Traders Pvt Ltd", "issue_date": "15/06/2023"}'
)

try:
    import pypdf
    _pypdf_available = True
except ImportError:
    _pypdf_available = False


def _extract_pdf_text(pdf_path: str) -> str:
    if not _pypdf_available:
        raise ImportError("pypdf not available")
    text_parts = []
    with open(pdf_path, "rb") as fh:
        reader = pypdf.PdfReader(fh)
        for page in reader.pages:
            try:
                page_text = page.extract_text()
            except Exception:
                page_text = ""
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def _describe_document_sync(image_path: str, strict_json: bool = False) -> dict | str:
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    b64 = __import__("base64").b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:image/jpeg;base64,{b64}"
    prompt = _VISION_STRICT_JSON_PROMPT if strict_json else (
        "Extract all text and key details visible in this official document. "
        "List: document type, name of business/person, registration numbers, "
        "dates, validity period, address. Do not interpret or assess — only "
        "extract what is visibly present."
    )
    completion = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
        max_tokens=600,
        timeout=60,
    )
    raw = completion.choices[0].message.content
    if strict_json:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {
                "document_type": None,
                "extracted_id": None,
                "business_name": None,
                "issue_date": None,
                "_parse_error": True,
                "_raw": cleaned[:500],
            }
    return raw


def _validate_gstin(raw_text: str, key_fields: dict, extraction_tier: str | None = None) -> dict:
    reg_number = key_fields.get("registration_number") or key_fields.get("extracted_id") or ""
    reg_number = str(reg_number).strip() if reg_number else ""
    if not reg_number:
        return {"verified": False, "reason": "No registration number found in GST certificate", "flag": "missing_gstin"}
    if not _GSTIN_PATTERN.match(reg_number.upper()):
        return {"verified": False, "reason": f"GSTIN format invalid: {reg_number}", "flag": "invalid_gstin_checksum"}
    checksum_ok, checksum_err = _validate_gstin_checksum(reg_number)
    if not checksum_ok:
        return {"verified": False, "reason": f"GSTIN checksum invalid: {checksum_err}", "flag": "invalid_gstin_checksum"}
    entity_name = key_fields.get("entity_name") or key_fields.get("business_name") or ""
    entity_name = str(entity_name).strip() if entity_name else ""
    if not entity_name or len(entity_name) < 2:
        return {"verified": False, "reason": "Entity/business name missing or too short in GST certificate", "flag": "invalid_gstin_checksum"}
    if extraction_tier != "tier2_vision" and len(raw_text) < 15:
        return {"verified": False, "reason": "Extracted text too short to be a valid GST certificate", "flag": "invalid_gstin_checksum"}
    return {"verified": True, "reason": "GSTIN format valid; entity name present; sufficient text extracted", "flag": None}


def _validate_udyam(raw_text: str, key_fields: dict, extraction_tier: str | None = None) -> dict:
    reg_number = key_fields.get("registration_number") or key_fields.get("extracted_id") or ""
    reg_number = str(reg_number).strip() if reg_number else ""
    if not reg_number:
        return {"verified": False, "reason": "No registration number found in Udyam certificate", "flag": "invalid_udyam_format"}
    if not _UDYAM_PATTERN.match(reg_number.upper()):
        return {"verified": False, "reason": f"Udyam registration number format invalid: {reg_number}", "flag": "invalid_udyam_format"}
    if extraction_tier != "tier2_vision" and len(raw_text) < 15:
        return {"verified": False, "reason": "Extracted text too short to be a valid Udyam certificate", "flag": "invalid_udyam_format"}
    return {"verified": True, "reason": "Udyam number format valid; sufficient text extracted", "flag": None}


def _validate_bank_statement(raw_text: str, key_fields: dict, extraction_tier: str | None = None) -> dict:
    dates = _BANK_DATE_PATTERN.findall(raw_text)
    amounts = _BANK_AMOUNT_PATTERN.findall(raw_text)
    if extraction_tier != "tier2_vision" and len(dates) < 2:
        return {"verified": False, "reason": "Insufficient date entries found for a bank statement"}
    numeric_amounts = []
    for a in amounts:
        try:
            cleaned = a.replace(",", "").replace("₹", "").replace("INR", "").strip()
            if cleaned:
                numeric_amounts.append(float(cleaned))
        except ValueError:
            continue
    if extraction_tier != "tier2_vision" and len(numeric_amounts) < 2:
        return {"verified": False, "reason": "Insufficient monetary amounts found for a bank statement"}
    entity_name = key_fields.get("entity_name") or key_fields.get("business_name") or ""
    entity_name = str(entity_name).strip() if entity_name else ""
    if not entity_name:
        return {"verified": False, "reason": "Account holder name missing in bank statement"}
    if extraction_tier == "tier2_vision":
        return {"verified": True, "reason": "Bank statement fields extracted via vision; manual review recommended for full validation"}
    return {"verified": True, "reason": f"Bank statement contains {len(dates)} date entries and {len(numeric_amounts)} amount entries"}


def _validate_trade_license(raw_text: str, key_fields: dict, extraction_tier: str | None = None) -> dict:
    reg_number = key_fields.get("registration_number") or key_fields.get("extracted_id") or ""
    reg_number = str(reg_number).strip() if reg_number else ""
    if not reg_number:
        return {"verified": False, "reason": "No license number found in trade license document"}
    if not _LICENSE_PATTERN.match(reg_number.upper()):
        return {"verified": False, "reason": f"License number format unrecognised: {reg_number}"}
    dates = _BANK_DATE_PATTERN.findall(raw_text)
    if extraction_tier != "tier2_vision" and len(dates) < 1:
        return {"verified": False, "reason": "No validity dates found in trade license"}
    if extraction_tier == "tier2_vision":
        return {"verified": True, "reason": "Trade license fields extracted via vision; manual review recommended for full validation"}
    return {"verified": True, "reason": "License number present; validity dates found"}


_VERIFIERS = {
    "gst_certificate": _validate_gstin,
    "udyam_certificate": _validate_udyam,
    "bank_statement": _validate_bank_statement,
    "trade_license": _validate_trade_license,
}


def _run_verifier(doc_type: str, raw_text: str, key_fields: dict, extraction_tier: str | None = None) -> dict:
    verifier = _VERIFIERS.get(doc_type)
    verification = {"verified": False, "reason": "No verifier defined for this document type", "flag": None}
    if verifier:
        try:
            verification = verifier(raw_text, key_fields, extraction_tier)
        except Exception as e:
            verification = {"verified": False, "reason": f"Verification error: {str(e)}", "flag": "verification_error"}
    if "flag" not in verification:
        verification["flag"] = None
    return verification


def _tier1_pdf(doc_type: str, doc_path: str) -> tuple[str, dict] | None:
    if not _pypdf_available:
        return None
    try:
        raw_text = _extract_pdf_text(doc_path)
    except Exception:
        return None
    if not raw_text or not raw_text.strip():
        return None
    if len(raw_text) < 15:
        return None
    key_fields = {}
    try:
        field_prompt = (
            "Given the following text extracted from a "
            f"{_DOC_TYPE_HINTS.get(doc_type, doc_type)}, "
            "extract key structured fields. Return ONLY a JSON object with keys: "
            "document_type, entity_name, registration_number, dates, validity_period, address. "
            "Use null for missing fields. Do not add extra text.\n\n"
            f"Text:\n{raw_text[:3000]}"
        )
        completion = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{"role": "user", "content": field_prompt}],
            max_tokens=300,
            timeout=30,
        )
        raw_fields = completion.choices[0].message.content.strip()
        if raw_fields.startswith("```"):
            raw_fields = raw_fields.split("```")[1]
            if raw_fields.startswith("json"):
                raw_fields = raw_fields[4:]
            raw_fields = raw_fields.strip()
        try:
            key_fields = json.loads(raw_fields)
        except json.JSONDecodeError:
            key_fields = {"raw_response": raw_fields}
    except Exception:
        key_fields = {}
    return raw_text, key_fields


def _tier2_vision(doc_type: str, doc_path: str) -> tuple[str, dict]:
    structured = _describe_document_sync(doc_path, strict_json=True)
    if isinstance(structured, dict) and structured.get("_parse_error"):
        raw_text = scrub_pii(structured.get("_raw", "") or "")
        key_fields = {"raw_response": structured.get("_raw", "")}
        return raw_text, key_fields
    if not isinstance(structured, dict):
        raw_text = scrub_pii(str(structured))
        return raw_text, {}
    extracted_id = structured.get("extracted_id") or ""
    business_name = structured.get("business_name") or ""
    issue_date = structured.get("issue_date") or ""
    raw_text_parts = []
    if extracted_id:
        raw_text_parts.append(f"Registration/ID: {extracted_id}")
    if business_name:
        raw_text_parts.append(f"Business/Person: {business_name}")
    if issue_date:
        raw_text_parts.append(f"Issue/Validity Date: {issue_date}")
    raw_text = scrub_pii("\n".join(raw_text_parts)) if raw_text_parts else ""
    key_fields = {
        "document_type": structured.get("document_type"),
        "registration_number": extracted_id if extracted_id else None,
        "entity_name": business_name if business_name else None,
        "dates": issue_date if issue_date else None,
    }
    return raw_text, key_fields


def _process_single_document(doc_type: str, doc_path: str) -> dict:
    filename = os.path.basename(doc_path)
    ext = os.path.splitext(filename)[1].lower()
    is_pdf = ext == ".pdf"
    tier_used = None
    raw_text = ""
    key_fields = {}
    error_msg = None

    if is_pdf:
        tier1 = _tier1_pdf(doc_type, doc_path)
        if tier1 is not None:
            raw_text, key_fields = tier1
            tier_used = "tier1_pdf"
        else:
            tier_used = "tier2_vision"
            try:
                raw_text, key_fields = _tier2_vision(doc_type, doc_path)
            except Exception as e:
                return {
                    "raw_text": "",
                    "document_type": _DOC_TYPE_HINTS.get(doc_type, doc_type),
                    "key_fields": {},
                    "verified": False,
                    "verification_reason": f"Vision fallback failed: {str(e)}",
                    "error": f"Vision fallback failed: {str(e)}",
                    "extraction_tier": None,
                }
    else:
        tier_used = "tier2_vision"
        try:
            raw_text, key_fields = _tier2_vision(doc_type, doc_path)
        except Exception as e:
            return {
                "raw_text": "",
                "document_type": _DOC_TYPE_HINTS.get(doc_type, doc_type),
                "key_fields": {},
                "verified": False,
                "verification_reason": f"Vision extraction failed: {str(e)}",
                "error": f"Vision extraction failed: {str(e)}",
                "extraction_tier": None,
            }

    verification = _run_verifier(doc_type, raw_text, key_fields, tier_used)

    return {
        "raw_text": raw_text,
        "document_type": _DOC_TYPE_HINTS.get(doc_type, doc_type),
        "key_fields": key_fields,
        "verified": verification.get("verified", False),
        "verification_reason": verification.get("reason", ""),
        "flag": verification.get("flag"),
        "extraction_tier": tier_used,
    }


def process_documents(doc_paths: dict) -> dict:
    """
    Process optional official documents using a low-memory 2-tier pipeline:
      Tier 1: pypdf digital text extraction + regex validation.
      Tier 2: Cloud vision fallback for scanned images/photos (no local OCR).

    Never raises. Always returns a dict with verified flags.
    """
    documents_processed = []
    documents_missing = []
    extracted = {}
    verification_signals = {
        "has_gst": False,
        "has_udyam": False,
        "has_bank_account": False,
        "has_trade_license": False,
        "documents_cross_checked": False,
        "document_confidence": "low",
    }

    try:
        for doc_type in [
            "gst_certificate",
            "udyam_certificate",
            "bank_statement",
            "aadhaar_card",
            "rent_agreement",
            "trade_license",
        ]:
            path = doc_paths.get(doc_type)
            if path is None:
                documents_missing.append(doc_type)
                continue

            if not os.path.isfile(path):
                documents_missing.append(doc_type)
                continue

            documents_processed.append(doc_type)
            try:
                result = _process_single_document(doc_type, path)
                extracted[doc_type] = result
                is_verified = result.get("verified", False)
                if doc_type == "gst_certificate":
                    verification_signals["has_gst"] = "error" not in result and is_verified
                elif doc_type == "udyam_certificate":
                    verification_signals["has_udyam"] = "error" not in result and is_verified
                elif doc_type == "bank_statement":
                    verification_signals["has_bank_account"] = "error" not in result and is_verified
                elif doc_type == "trade_license":
                    verification_signals["has_trade_license"] = "error" not in result and is_verified
            except Exception as e:
                extracted[doc_type] = {
                    "raw_text": "",
                    "document_type": _DOC_TYPE_HINTS.get(doc_type, doc_type),
                    "key_fields": {},
                    "verified": False,
                    "verification_reason": str(e),
                    "error": str(e),
                    "extraction_tier": None,
                }

        verified_count = sum(
            1 for doc_type, result in extracted.items()
            if result.get("verified", False)
        )
        if verified_count >= 3:
            verification_signals["document_confidence"] = "high"
        elif verified_count >= 1:
            verification_signals["document_confidence"] = "medium"

        if documents_processed:
            verification_signals["documents_cross_checked"] = True

    except Exception:
        pass

    return {
        "documents_processed": documents_processed,
        "documents_missing": documents_missing,
        "extracted": extracted,
        "verification_signals": verification_signals,
    }
