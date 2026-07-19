from dotenv import load_dotenv
load_dotenv()

import os
import json
import time
from faster_whisper import WhisperModel
from openai import OpenAI
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
or_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
TEXT_MODEL = "ibm-granite/granite-4.1-8b"
_whisper_model = None
def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model
def process_voice(audio_path: str) -> dict:
    model = _get_whisper()
    t0 = time.time()
    segments, _ = model.transcribe(audio_path)
    t1 = time.time()
    print(f"[voice_agent] whisper transcribe took {t1 - t0:.2f}s", flush=True)
    transcript = " ".join(seg.text.strip() for seg in segments)
    prompt = (
        "Extract ONLY the following if mentioned: business type, "
        "products/services, years operating, location. Do not infer tone, "
        "confidence, honesty, or emotional state. Return strict JSON with "
        "keys business_type, products, years_operating, location. Omit a "
        "key entirely if not mentioned.\n\nTranscript:\n" + transcript
    )
    completion = or_client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
    )
    t2 = time.time()
    print(f"[voice_agent] openrouter extraction took {t2 - t1:.2f}s", flush=True)
    raw = completion.choices[0].message.content
    raw_clean = raw.strip()
    if raw_clean.startswith("```"):
        raw_clean = raw_clean.split("```")[1]
        if raw_clean.startswith("json"):
            raw_clean = raw_clean[4:]
        raw_clean = raw_clean.strip()
    try:
        extracted = json.loads(raw_clean)
    except json.JSONDecodeError:
        extracted = {"raw_response": raw}
    return {
        "transcript": transcript,
        "extracted": extracted,
        "label": "officer observation, unverified",
    }
