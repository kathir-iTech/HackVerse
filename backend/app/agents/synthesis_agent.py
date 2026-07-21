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
- Output ONLY valid JSON with no markdown fences or extra text."""


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
        evidence_parts.append(f"[transactions: {json.dumps(transaction_result)}]")

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
- missing_inputs (list of strings — which of photos / voice / transactions were missing)"""

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
    except Exception:
        report = {"error": "synthesis failed", "raw_response": raw}

    report["missing_inputs"] = missing
    return report
