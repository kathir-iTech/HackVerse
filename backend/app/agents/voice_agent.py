import sys
import shutil

from dotenv import load_dotenv
load_dotenv()

import os
import json
import time
from faster_whisper import WhisperModel
from openai import OpenAI
from app.utils.privacy import scrub_pii

if not shutil.which("ffmpeg"):
    print("[voice_agent] WARNING: ffmpeg not found \u2014 browser recordings in webm/ogg may not transcribe correctly")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    print("ERROR: OPENROUTER_API_KEY environment variable is not set.", file=sys.stderr)
    OPENROUTER_API_KEY = ""
or_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
TEXT_MODEL = "ibm-granite/granite-4.1-8b"
MIN_TRANSCRIPT_CHARS = 10
_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
    return _whisper_model


def _extract_from_text(transcript_safe: str) -> dict:
    prompt = (
        "Extract ONLY the following if mentioned: business type, "
        "products/services, years operating, location. Do not infer tone, "
        "confidence, honesty, or emotional state. Return strict JSON with "
        "keys business_type, products, years_operating, location. Omit a "
        "key entirely if not mentioned.\n\nTranscript:\n" + transcript_safe
    )
    try:
        completion = or_client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            timeout=30,
        )
    except Exception as e:
        return {"error": "voice processing failed", "detail": str(e)}
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
    return extracted


def process_voice(audio_path: str, language: str | None = None) -> dict:
    # Sanitize language: "auto", empty string, and invalid values → None (Whisper auto-detect)
    _VALID_LANGS = {
        "af","am","ar","as","az","ba","be","bg","bn","bo","br","bs","ca","cs","cy","da","de",
        "el","en","es","et","eu","fa","fi","fo","fr","gl","gu","ha","haw","he","hi","hr","ht",
        "hu","hy","id","is","it","ja","jw","ka","kk","km","kn","ko","la","lb","ln","lo","lt",
        "lv","mg","mi","mk","ml","mn","mr","ms","mt","my","ne","nl","nn","no","oc","pa","pl",
        "ps","pt","ro","ru","sa","sd","si","sk","sl","sn","so","sq","sr","su","sv","sw","ta",
        "te","tg","th","tk","tl","tr","tt","uk","ur","uz","vi","yi","yo","zh","yue",
    }
    if not language or language.strip().lower() in ("", "auto"):
        language = None
    elif language.strip().lower() not in _VALID_LANGS:
        print(f"[voice_agent] WARNING: unsupported language code '{language}', falling back to auto-detect", file=sys.stderr)
        language = None
    model = _get_whisper()
    t0 = time.time()
    try:
        segments, info = model.transcribe(audio_path, language=language)
    except Exception as e:
        return {"error": "voice processing failed", "detail": str(e)}
    t1 = time.time()
    print(f"[voice_agent] whisper transcribe took {t1 - t0:.2f}s", flush=True)
    transcript = " ".join(seg.text.strip() for seg in segments)
    if len(transcript.strip()) < MIN_TRANSCRIPT_CHARS:
        return {
            "transcription_failed": True,
            "transcript": "",
            "language_detected": getattr(info, "language", None),
            "error": "voice transcription failed or returned no speech",
        }
    transcript_safe = scrub_pii(transcript)
    extracted = _extract_from_text(transcript_safe)
    if "error" in extracted:
        return extracted
    t2 = time.time()
    print(f"[voice_agent] openrouter extraction took {t2 - t1:.2f}s", flush=True)
    return {
        "transcript_pii_scrubbed": transcript_safe,
        "extracted": extracted,
        "label": "officer observation, unverified",
        "language_detected": getattr(info, "language", None),
    }


def process_manual_text(text: str) -> dict:
    if len(text.strip()) < MIN_TRANSCRIPT_CHARS:
        return {
            "transcription_failed": True,
            "transcript": "",
            "error": "manual field notes too short to extract information",
        }
    transcript_safe = scrub_pii(text)
    extracted = _extract_from_text(transcript_safe)
    if "error" in extracted:
        return extracted
    return {
        "transcript_pii_scrubbed": transcript_safe,
        "extracted": extracted,
        "label": "manual field notes, officer-provided",
    }
