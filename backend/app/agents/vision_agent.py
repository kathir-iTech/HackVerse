from dotenv import load_dotenv
load_dotenv()

import os
import base64
from openai import OpenAI

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


def _describe_image(image_path: str) -> str | None:
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_uri = f"data:image/jpeg;base64,{b64}"
    try:
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
        )
    except Exception as e:
        print(f"[vision_agent] _describe_image failed: {e}", file=sys.stderr)
        return None
    return completion.choices[0].message.content


def analyze_photos(image_paths: list[str]) -> dict:
    per_image = []
    for path in image_paths:
        desc = _describe_image(path)
        if desc is None:
            return {"error": "vision processing failed"}
        per_image.append({"file": os.path.basename(path), "description": desc})
    try:
        combined = "\n".join(f"- {d['description']}" for d in per_image)
        completion = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[{"role": "user", "content": SUMMARY_PROMPT_PREFIX + combined}],
            max_tokens=300,
        )
        summary = completion.choices[0].message.content
    except Exception as e:
        print(f"[vision_agent] summary call failed: {e}", file=sys.stderr)
        return {"error": "vision processing failed"}
    return {"per_image": per_image, "summary": summary}
