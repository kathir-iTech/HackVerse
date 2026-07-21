import json
import os

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
  not just qualitatively."""


def _strip_fences(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    return cleaned


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
        evidence_parts.append(f"[voice: {json.dumps(voice_result)}]")

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
- discrepancy_flags (list of strings — each describing one cross-source contradiction found, or empty list if none)"""

    raw = None
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=600,
        )
        raw = completion.choices[0].message.content
        cleaned = _strip_fences(raw)
        report = json.loads(cleaned)
    except Exception as e:
        report = {"error": "synthesis failed", "detail": str(e), "raw_response": raw}

    report["missing_inputs"] = missing
    if "discrepancy_flags" not in report:
        report["discrepancy_flags"] = []
    return report
