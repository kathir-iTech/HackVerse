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
TEXT_MODEL = "google/gemini-2.5-flash"

DOCUMENT_EXTRACTION_PROMPT = (
    "Extract all text and key details visible in this official document. "
    "List: document type, name of business/person, registration numbers, "
    "dates, validity period, address. Do not interpret or assess — only "
    "extract what is visibly present."
)

_DOC_TYPE_HINTS = {
    "gst_certificate": "GST Certificate",
    "udyam_certificate": "Udyam/MSME Certificate",
    "bank_statement": "Bank Statement",
    "aadhaar_card": "Aadhaar Card",
    "rent_agreement": "Rent Agreement",
    "trade_license": "Trade License",
}

_GSTIN_PATTERN = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9][Z][A-Z0-9]$')
_UDYAM_PATTERN = re.compile(r'^UDYAM-[0-9]{2}-[0-9]{2}-[0-9]{7}$')
_BANK_DATE_PATTERN = re.compile(r'\b(?:\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})\b')
_BANK_AMOUNT_PATTERN = re.compile(r'(?:INR\s*|₹\s*)?[\d,]+(?:\.\d{1,2})?')
_LICENSE_PATTERN = re.compile(r'[A-Z0-9/\-]{5,20}')

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


def _describe_document_sync(image_path: str) -> str:
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    b64 = __import__("base64").b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:image/jpeg;base64,{b64}"
    completion = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": DOCUMENT_EXTRACTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
        max_tokens=600,
        timeout=60,
    )
    return completion.choices[0].message.content


def _validate_gstin(raw_text: str, key_fields: dict) -> dict:
    reg_number = key_fields.get("registration_number") or ""
    reg_number = str(reg_number).strip() if reg_number else ""
    if not reg_number:
        return {"verified": False, "reason": "No registration number found in GST certificate"}
    if not _GSTIN_PATTERN.match(reg_number.upper()):
        return {"verified": False, "reason": f"GSTIN format invalid: {reg_number}"}
    entity_name = key_fields.get("entity_name") or ""
    entity_name = str(entity_name).strip() if entity_name else ""
    if not entity_name or len(entity_name) < 2:
        return {"verified": False, "reason": "Entity/business name missing or too short in GST certificate"}
    if len(raw_text) < 50:
        return {"verified": False, "reason": "Extracted text too short to be a valid GST certificate"}
    return {"verified": True, "reason": "GSTIN format valid; entity name present; sufficient text extracted"}


def _validate_udyam(raw_text: str, key_fields: dict) -> dict:
    reg_number = key_fields.get("registration_number") or ""
    reg_number = str(reg_number).strip() if reg_number else ""
    if not reg_number:
        return {"verified": False, "reason": "No registration number found in Udyam certificate"}
    if not _UDYAM_PATTERN.match(reg_number.upper()):
        return {"verified": False, "reason": f"Udyam registration number format invalid: {reg_number}"}
    if len(raw_text) < 50:
        return {"verified": False, "reason": "Extracted text too short to be a valid Udyam certificate"}
    return {"verified": True, "reason": "Udyam number format valid; sufficient text extracted"}


def _validate_bank_statement(raw_text: str, key_fields: dict) -> dict:
    dates = _BANK_DATE_PATTERN.findall(raw_text)
    amounts = _BANK_AMOUNT_PATTERN.findall(raw_text)
    if len(dates) < 2:
        return {"verified": False, "reason": "Insufficient date entries found for a bank statement"}
    numeric_amounts = []
    for a in amounts:
        try:
            cleaned = a.replace(",", "").replace("₹", "").replace("INR", "").strip()
            if cleaned:
                numeric_amounts.append(float(cleaned))
        except ValueError:
            continue
    if len(numeric_amounts) < 2:
        return {"verified": False, "reason": "Insufficient monetary amounts found for a bank statement"}
    entity_name = key_fields.get("entity_name") or ""
    entity_name = str(entity_name).strip() if entity_name else ""
    if not entity_name:
        return {"verified": False, "reason": "Account holder name missing in bank statement"}
    return {"verified": True, "reason": f"Bank statement contains {len(dates)} date entries and {len(numeric_amounts)} amount entries"}


def _validate_trade_license(raw_text: str, key_fields: dict) -> dict:
    reg_number = key_fields.get("registration_number") or ""
    reg_number = str(reg_number).strip() if reg_number else ""
    if not reg_number:
        return {"verified": False, "reason": "No license number found in trade license document"}
    if not _LICENSE_PATTERN.match(reg_number.upper()):
        return {"verified": False, "reason": f"License number format unrecognised: {reg_number}"}
    dates = _BANK_DATE_PATTERN.findall(raw_text)
    if len(dates) < 1:
        return {"verified": False, "reason": "No validity dates found in trade license"}
    return {"verified": True, "reason": "License number present; validity dates found"}


_VERIFIERS = {
    "gst_certificate": _validate_gstin,
    "udyam_certificate": _validate_udyam,
    "bank_statement": _validate_bank_statement,
    "trade_license": _validate_trade_license,
}


def _process_single_document(doc_type: str, doc_path: str) -> dict:
    filename = os.path.basename(doc_path)
    ext = os.path.splitext(filename)[1].lower()
    raw_text = ""
    is_pdf = ext == ".pdf"
    error_msg = None

    if is_pdf:
        if not _pypdf_available:
            return {
                "raw_text": "",
                "document_type": _DOC_TYPE_HINTS.get(doc_type, doc_type),
                "key_fields": {},
                "verified": False,
                "verification_reason": "PDF processing unavailable (pypdf not installed)",
                "error": "PDF processing unavailable (pypdf not installed)",
            }
        try:
            raw_text = _extract_pdf_text(doc_path)
        except Exception as e:
            return {
                "raw_text": "",
                "document_type": _DOC_TYPE_HINTS.get(doc_type, doc_type),
                "key_fields": {},
                "verified": False,
                "verification_reason": f"PDF extraction failed: {str(e)}",
                "error": f"PDF extraction failed: {str(e)}",
            }
    else:
        try:
            raw_text = _describe_document_sync(doc_path)
        except Exception as e:
            return {
                "raw_text": "",
                "document_type": _DOC_TYPE_HINTS.get(doc_type, doc_type),
                "key_fields": {},
                "verified": False,
                "verification_reason": f"Vision extraction failed: {str(e)}",
                "error": f"Vision extraction failed: {str(e)}",
            }

    scrubbed = scrub_pii(raw_text)

    key_fields = {}
    try:
        field_prompt = (
            "Given the following text extracted from a "
            f"{_DOC_TYPE_HINTS.get(doc_type, doc_type)}, "
            "extract key structured fields. Return ONLY a JSON object with keys: "
            "document_type, entity_name, registration_number, dates, validity_period, address. "
            "Use null for missing fields. Do not add extra text.\n\n"
            f"Text:\n{scrubbed[:3000]}"
        )
        completion = client.chat.completions.create(
            model=TEXT_MODEL,
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

    verifier = _VERIFIERS.get(doc_type)
    verification = {"verified": False, "reason": "No verifier defined for this document type"}
    if verifier:
        try:
            verification = verifier(scrubbed, key_fields)
        except Exception as e:
            verification = {"verified": False, "reason": f"Verification error: {str(e)}"}

    return {
        "raw_text": scrubbed,
        "document_type": _DOC_TYPE_HINTS.get(doc_type, doc_type),
        "key_fields": key_fields,
        "verified": verification.get("verified", False),
        "verification_reason": verification.get("reason", ""),
    }


def process_documents(doc_paths: dict) -> dict:
    """
    Process optional official documents. Returns extraction results
    and verification signals. Never raises — always returns a dict.
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
