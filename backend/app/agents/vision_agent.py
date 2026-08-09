from dotenv import load_dotenv
load_dotenv()

import os
import sys
import asyncio
import base64
from openai import OpenAI


def compute_image_hash(image_path: str) -> str | None:
    try:
        from PIL import Image
        from imagehash import average_hash
        img = Image.open(image_path)
        return str(average_hash(img))
    except Exception:
        return None

api_key = os.environ.get("OPENROUTER_API_KEY")
if not api_key:
    print("ERROR: OPENROUTER_API_KEY environment variable is not set.", file=sys.stderr)
    api_key = ""

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key
)
VISION_MODEL = "google/gemini-2.5-flash"
TEXT_MODEL = "google/gemini-2.5-flash"
DESCRIBE_PROMPT = (
    "Describe the visible inventory, shop condition, and activity level in "
    "this image factually. Do not judge quality or health, only describe "
    "what is visible."
)
SUMMARY_PROMPT_PREFIX = (
    "Based on these checkpoint descriptions, state only which visible "
    "categories of inventory appear similar or different across images. "
    "Do not conclude anything about business health.\n\n"
)


def _describe_image_sync(image_path: str) -> str:
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{b64}"
        completion = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": DESCRIBE_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            max_tokens=300,
            timeout=30,
        )
        return completion.choices[0].message.content or ""
    except Exception:
        return "Image could not be analyzed"


BLANK_IMAGE_TERMS = (
    "blank",
    "blank screen",
    "empty screen",
    "no image",
    "no visible",
    "no content",
    "no objects",
    "no discernible",
    "uniform color",
    "solid color",
    "out of focus",
    "blurry",
    "abstract texture",
    "no commercial",
    "no inventory",
    "no shop",
    "no products",
    "no retail",
    "no stock",
    "no merchandise",
    "unintelligible",
)


def _classify_usable_evidence(description: str) -> tuple[bool, str | None]:
    if not description or not description.strip():
        return False, "blank_photo_evidence"
    lower = description.lower()
    for term in BLANK_IMAGE_TERMS:
        if term in lower:
            return False, "blank_photo_evidence"
    return True, None


async def _describe_image(image_path: str) -> str:
    return await asyncio.to_thread(_describe_image_sync, image_path)


def _summarize(combined: str) -> str:
    try:
        completion = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[{"role": "user", "content": SUMMARY_PROMPT_PREFIX + combined}],
            max_tokens=300,
            timeout=30,
        )
        return completion.choices[0].message.content or "No inventory summary available"
    except Exception:
        return "No inventory summary available"


async def analyze_photos(image_paths: list[str]) -> dict:
    tasks = [_describe_image(path) for path in image_paths]
    descriptions = await asyncio.gather(*tasks, return_exceptions=True)

    per_image = []
    failures = []
    for path, result in zip(image_paths, descriptions):
        if isinstance(result, Exception):
            failures.append(result)
            per_image.append({
                "file": os.path.basename(path),
                "description": None,
                "usable_evidence": False,
                "invalid_photo_evidence": "vision processing failed",
                "error": "vision processing failed",
                "detail": str(result),
            })
        else:
            usable, flag = _classify_usable_evidence(result)
            entry: dict = {
                "file": os.path.basename(path),
                "description": result,
                "usable_evidence": usable,
            }
            if not usable:
                entry["invalid_photo_evidence"] = flag
            per_image.append(entry)

    successful = [d for d in per_image if "error" not in d and d.get("usable_evidence")]
    if not successful:
        detail = str(failures[0]) if failures else "no usable images could be described"
        return {
            "error": "vision processing failed",
            "detail": detail,
            "usable_evidence": False,
            "invalid_photo_evidence": "blank_photo_evidence",
        }

    try:
        combined = "\n".join(f"- {d['description']}" for d in successful)
        summary = await asyncio.to_thread(_summarize, combined)
    except Exception as e:
        return {"error": "vision processing failed", "detail": str(e)}
    return {"per_image": per_image, "summary": summary}
