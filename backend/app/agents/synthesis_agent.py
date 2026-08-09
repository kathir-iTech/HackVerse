import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    print("ERROR: OPENROUTER_API_KEY environment variable is not set.", file=sys.stderr)
    api_key = ""

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)
MODEL = "ibm-granite/granite-4.1-8b"

SYSTEM_PROMPT = """You are a financial assessment assistant for MSME lending. \
You receive evidence from multiple sources and must produce a strict JSON assessment. \
Rules:
- Do not invent numeric scores or currency amounts.
- Base bands only on the evidence provided.
- If evidence is thin or missing, favor "Further assessment required".
- Output ONLY valid JSON with no markdown fences or extra text.
- Actively cross-check the evidence sources against each other for contradictions.
  Look specifically for: (1) stock/inventory levels visible in photos vs sales volume implied by transactions,
  (2) business tenure claimed in the voice note vs the actual time span covered by transaction data,
  (3) revenue level vs digital activity level plausibility,
  (4) any other factual inconsistency between what was said, shown, and recorded.
  For each contradiction found, phrase it as a neutral observation for the officer to verify,
  never as an accusation. If no evidence conflicts, or if there isn't enough evidence to
  cross-check (e.g. only one source provided), return an empty list.
- If the voice note or other evidence states a business tenure (e.g. 'X months/years operating')
  that is inconsistent with the actual transaction date span provided above, this MUST be flagged
  in discrepancy_flags. Compare the stated tenure against the actual number of days explicitly,
  not just qualitatively.
- For the source_agreement field, assess each pair of evidence sources independently:
  - photo_voice: Does what's visible in the photos (inventory level, shop activity) plausibly match
    what the business owner claimed in the voice note (business type, scale, products)?
  - photo_transactions: Does the apparent business scale from photos plausibly match the transaction
    volumes and patterns? E.g. a shop showing minimal inventory but high transaction inflows is a conflict.
  - voice_transactions: Does the tenure and business description from the voice note align with the
    transaction date range, volumes, and trends?
  - photo_documents: Do the business details in any provided official documents (e.g. GST certificate
    business name/address) match what is visible in the photos?
  - voice_documents: Do the details from official documents (business name, address, registration
    numbers) match what the officer described in the voice note?
  - transaction_documents: Do the transaction amounts and patterns roughly align with what the
    bank statement shows?
  If either source in a pair is missing, use "insufficient_data". Otherwise choose "agree" or "conflict"
  based on clear inconsistency — if you're uncertain, prefer "agree".
- For the onboarding_pathway field: if assessment_band is "Suitable for micro-loan assessment" or
  "Suitable for higher assessment range", generate a list of 2-4 specific actionable onboarding steps
  the officer should share with the vendor. Use only real Indian government schemes with accurate details:
  - Jan Dhan Yojana: zero-balance savings account, available at any nationalized bank, free, no minimum balance
  - Udyam Registration: free MSME registration at udyamregistration.gov.in, no GST needed for turnover under ₹40 lakh, takes 10 minutes with just Aadhaar
  - PM SVANidhi: street vendor working capital loan scheme, no GST needed, loans from ₹10,000-₹50,000
  - MUDRA Shishu: loans up to ₹50,000 for micro enterprises, requires basic savings account
  - GST Registration: required if annual turnover exceeds ₹20 lakh (services) or ₹40 lakh (goods), at gst.gov.in
  If has_gst is false and the assessment is suitable, add "Register for GST at gst.gov.in if annual turnover exceeds ₹20 lakh (services) or ₹40 lakh (goods)".
  If has_udyam is false and the assessment is suitable, add "Register for Udyam at udyamregistration.gov.in — free MSME registration, takes 10 minutes with Aadhaar".
  If assessment_band is "Further assessment required", return an empty list — no premature recommendations.
  Each step should be one clear sentence: what it is, where to do it, what's needed.
- For the officer_guidance field: write a 2-3 sentence paragraph addressed directly to the field officer (not the lender),
  written in plain simple English, telling them specifically what to verify or follow up on based on the evidence gaps
  and discrepancies found. Example: 'The owner claims 3 years of operation but transaction records only cover 81 days —
  ask to see older passbook entries or ledger records. Inventory appears well-stocked and consistent. Priority follow-up:
  verify business tenure with supporting documents.' Never repeat the assessment band values — focus only on actionable next steps.
- For the reasoning_trace field: provide an object with keys revenue_consistency_reasoning, inventory_observation_reasoning,
  digital_activity_reasoning — each a single sentence explaining specifically why that band value was chosen based on the
  evidence provided. Example: 'Revenue Consistency rated Moderate because transaction volatility is high despite positive
  inflow trend.' Keep each sentence under 20 words.
- For document_confidence: assess based on how many official documents were provided.
  "high" if 3 or more documents, "medium" if 1-2 documents, "low" if no documents provided."""


def _extract_json_block(raw: str) -> str | None:
    """Extract the content between the first ``` or ```json fence and the next ```.

    Handles responses where Granite prepends prose like "**Assessment JSON**\\n\\n```json\\n{...}\\n```".
    Returns None if no fence is present, so callers can fall back to the full response.
    """
    if not raw:
        return None
    opening = raw.find("```")
    if opening == -1:
        return None
    content_start = raw.find("\n", opening)
    if content_start == -1:
        content_start = opening + 3
    else:
        content_start += 1
    closing = raw.find("```", content_start)
    if closing == -1:
        return None
    return raw[content_start:closing].strip()


def synthesize_report(
    vision_result: dict | None,
    voice_result: dict | None,
    transaction_result: dict | None,
    rag_context: list,
    document_result: dict | None = None,
) -> dict:
    evidence_parts = []
    missing = []

    if vision_result is None or "error" in vision_result:
        missing.append("photos")
        evidence_parts.append("[photos: missing]")
    else:
        evidence_parts.append(f"[photos: {json.dumps(vision_result)}]")

    if voice_result is None or "error" in voice_result:
        missing.append("voice")
        evidence_parts.append("[voice: missing]")
    else:
        voice_evidence = dict(voice_result)
        if "transcript_pii_scrubbed" in voice_evidence:
            voice_evidence["transcript"] = voice_evidence["transcript_pii_scrubbed"]
        evidence_parts.append(f"[voice: {json.dumps(voice_evidence)}]")

    if transaction_result is None or "error" in transaction_result:
        missing.append("transactions")
        evidence_parts.append("[transactions: missing]")
    else:
        txn_date_info = ""
        if transaction_result.get("date_range_days") is not None:
            txn_date_info = f" [Transaction records span {transaction_result['date_range_days']} days (from {transaction_result.get('earliest_date', '?')} to {transaction_result.get('latest_date', '?')}).]"
        evidence_parts.append(f"[transactions: {json.dumps(transaction_result)}{txn_date_info}]")

    if document_result and document_result.get("extracted"):
        doc_extracted = document_result["extracted"]
        doc_lines = []
        for doc_type, doc_info in doc_extracted.items():
            kf = doc_info.get("key_fields", {})
            doc_lines.append(
                f"  - {doc_info.get('document_type', doc_type)}: "
                f"entity={kf.get('entity_name', 'N/A')}, "
                f"reg_no={kf.get('registration_number', 'N/A')}, "
                f"address={kf.get('address', 'N/A')}"
            )
        evidence_parts.append(
            "[Official Documents Provided:\n" + "\n".join(doc_lines) + "]"
        )
    else:
        evidence_parts.append("[official documents: none provided]")

    rag_block = "\n".join(c["content"] for c in rag_context) if rag_context else "[no RAG context retrieved]"

    user_prompt = f"""Available evidence:
{" ".join(evidence_parts)}

RAG context (SIDBI / RBI schemes):
{rag_block}

Output strict JSON with these keys:
- business_type (string or null)
- revenue_consistency_band ("Low" / "Moderate" / "Strong")
- inventory_observation_band ("Low" / "Moderate" / "Strong")
- digital_activity_band ("Low" / "Moderate" / "Strong")
- relevant_scheme_note (one sentence referencing the RAG context)
- assessment_band ("Further assessment required" / "Suitable for micro-loan assessment" / "Suitable for higher assessment range")
- evidence_summary (list of short evidence strings)
- missing_inputs (list of strings — which of photos / voice / transactions / documents were missing)
- discrepancy_flags (list of strings — each describing one cross-source contradiction found, or empty list if none)
- source_agreement (object with keys photo_voice, photo_transactions, voice_transactions, photo_documents, voice_documents, transaction_documents — each valued "agree" / "conflict" / "insufficient_data")
- onboarding_pathway (list of 2-4 strings — real Indian government scheme onboarding steps, or empty list if assessment_band is "Further assessment required")
- officer_guidance (a 2-3 sentence plain-language paragraph for the field officer with specific follow-up verification steps — never repeat the band values)
- reasoning_trace (object with keys revenue_consistency_reasoning, inventory_observation_reasoning, digital_activity_reasoning — one sentence each under 20 words)
- document_confidence ("high" / "medium" / "low")"""

    raw = None
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=900,
            timeout=30,
        )
        raw = completion.choices[0].message.content
        report = None
        fenced = _extract_json_block(raw)
        if fenced is not None:
            try:
                report = json.loads(fenced)
            except json.JSONDecodeError:
                report = None
        if report is None:
            report = json.loads(raw.strip())
    except Exception as e:
        report = {"error": "synthesis failed", "detail": str(e), "raw_response": raw}

    if not isinstance(report, dict):
        return {"error": "synthesis failed", "detail": "LLM returned non-dict response", "raw_response": str(report)}

    report["missing_inputs"] = missing

    if "discrepancy_flags" in report and not isinstance(report["discrepancy_flags"], list):
        report["discrepancy_flags"] = [str(report["discrepancy_flags"])] if report["discrepancy_flags"] else []

    if "evidence_summary" in report and not isinstance(report["evidence_summary"], list):
        report["evidence_summary"] = [str(report["evidence_summary"])] if report["evidence_summary"] else []

    if "source_agreement" in report and not isinstance(report["source_agreement"], dict):
        report["source_agreement"] = {"photo_voice": "insufficient_data", "photo_transactions": "insufficient_data", "voice_transactions": "insufficient_data", "photo_documents": "insufficient_data", "voice_documents": "insufficient_data", "transaction_documents": "insufficient_data"}

    report.setdefault("discrepancy_flags", [])
    report.setdefault("document_confidence", "low")

    if "onboarding_pathway" in report and not isinstance(report["onboarding_pathway"], list):
        report["onboarding_pathway"] = []
    report.setdefault("onboarding_pathway", [])

    if "officer_guidance" in report and not isinstance(report["officer_guidance"], str):
        report["officer_guidance"] = str(report["officer_guidance"])
    report.setdefault("officer_guidance", "")

    if "reasoning_trace" in report and not isinstance(report["reasoning_trace"], dict):
        report["reasoning_trace"] = {}
    report.setdefault("reasoning_trace", {})

    DEFAULT_AGREEMENT = {"photo_voice": "insufficient_data", "photo_transactions": "insufficient_data", "voice_transactions": "insufficient_data", "photo_documents": "insufficient_data", "voice_documents": "insufficient_data", "transaction_documents": "insufficient_data"}
    if "source_agreement" not in report or not isinstance(report["source_agreement"], dict):
        report["source_agreement"] = dict(DEFAULT_AGREEMENT)
    else:
        for k in ("photo_voice", "photo_transactions", "voice_transactions", "photo_documents", "voice_documents", "transaction_documents"):
            if report["source_agreement"].get(k) not in ("agree", "conflict", "insufficient_data"):
                report["source_agreement"][k] = "insufficient_data"

    if "error" not in report:
        BAND_VALUES = {"Low", "Moderate", "Strong"}
        ASSESSMENT_VALUES = {
            "Further assessment required",
            "Suitable for micro-loan assessment",
            "Suitable for higher assessment range",
        }
        for key in ("revenue_consistency_band", "inventory_observation_band", "digital_activity_band"):
            if report.get(key) not in BAND_VALUES:
                report[key] = "Further assessment required"
        if report.get("assessment_band") not in ASSESSMENT_VALUES:
            report["assessment_band"] = "Further assessment required"
        if report.get("document_confidence") not in ("high", "medium", "low"):
            report["document_confidence"] = "low"
    return report
