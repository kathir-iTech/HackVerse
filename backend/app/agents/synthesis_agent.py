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
  If either source in a pair is missing, use "insufficient_data". Otherwise choose "agree" or "conflict"
  based on clear inconsistency — if you're uncertain, prefer "agree".
- For the onboarding_pathway field: if assessment_band is "Suitable for micro-loan assessment" or
  "Suitable for higher assessment range", generate a list of 2-4 specific actionable onboarding steps
  the officer should share with the vendor. Use only real Indian government schemes with accurate details:
  - Jan Dhan Yojana: zero-balance savings account, available at any nationalized bank, free, no minimum balance
  - Udyam Registration: free MSME registration at udyamregistration.gov.in, no GST needed for turnover under ₹40 lakh, takes 10 minutes with just Aadhaar
  - PM SVANidhi: street vendor working capital loan scheme, no GST needed, loans from ₹10,000-₹50,000
  - MUDRA Shishu: loans up to ₹50,000 for micro enterprises, requires basic savings account
  If assessment_band is "Further assessment required", return an empty list — no premature recommendations.
  Each step should be one clear sentence: what it is, where to do it, what's needed."""


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
- missing_inputs (list of strings — which of photos / voice / transactions were missing)
- discrepancy_flags (list of strings — each describing one cross-source contradiction found, or empty list if none)
- source_agreement (object with keys photo_voice, photo_transactions, voice_transactions — each valued "agree" / "conflict" / "insufficient_data")
- onboarding_pathway (list of 2-4 strings — real Indian government scheme onboarding steps, or empty list if assessment_band is "Further assessment required")"""

    raw = None
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=600,
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
        report["source_agreement"] = {"photo_voice": "insufficient_data", "photo_transactions": "insufficient_data", "voice_transactions": "insufficient_data"}

    report.setdefault("discrepancy_flags", [])

    if "onboarding_pathway" in report and not isinstance(report["onboarding_pathway"], list):
        report["onboarding_pathway"] = []
    report.setdefault("onboarding_pathway", [])

    DEFAULT_AGREEMENT = {"photo_voice": "insufficient_data", "photo_transactions": "insufficient_data", "voice_transactions": "insufficient_data"}
    if "source_agreement" not in report or not isinstance(report["source_agreement"], dict):
        report["source_agreement"] = dict(DEFAULT_AGREEMENT)
    else:
        for k in ("photo_voice", "photo_transactions", "voice_transactions"):
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
    return report
