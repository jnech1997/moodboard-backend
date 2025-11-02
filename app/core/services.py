import os
import sys
import base64
import logging
from typing import List

import requests
from openai import OpenAI

# Environment
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PEXEL_API_KEY = os.getenv("PEXEL_API_KEY")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)


# --- Moderation and Embedding Utilities --- #


async def check_text_safe(text: str) -> bool:
    """Use OpenAI moderation to check text content."""
    logger.info("Running text safety check")
    mod = client.moderations.create(
        model="omni-moderation-latest",
        input=text,
    )
    return not mod.results[0].flagged


async def get_text_embedding(text: str) -> List[float]:
    """Generate a 1536-dim text embedding using OpenAI's small embedding model."""
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


# --- Image Moderation and Captioning --- #


async def check_image_safe_url(url: str) -> bool:
    """Use OpenAI moderation to check a remote image via its URL."""
    try:
        response = client.moderations.create(
            model="omni-moderation-latest",
            input=[{"type": "image_url", "image_url": {"url": url}}],
        )
        return not response.results[0].flagged
    except Exception as e:
        logger.info(f"Moderation failed for image URL: {e}")
        return False


async def check_image_safe(image_path: str) -> bool:
    """Check if a local image is safe for work via OpenAI moderation."""
    with open(image_path, "rb") as img:
        img_b64 = base64.b64encode(img.read()).decode("utf-8")

    try:
        caption_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Respond 'safe' if the image is safe for work, "
                        "or 'unsafe' otherwise."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image briefly."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                        },
                    ],
                },
            ],
        )
        is_flagged = str(caption_resp.choices[0].message.content).strip().lower() == "unsafe"
        return not is_flagged
    except Exception as e:
        logger.error(f"Error processing image for moderation: {e}")
        return False


def encode_image(image_path: str) -> str:
    """Return base64 representation of a local image."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


async def generate_image_caption_url(url: str) -> str:
    """Generate a poetic image caption based on a remote image URL."""
    try:
        res = requests.get(url, allow_redirects=True)
        completion = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": "You describe images briefly and clearly.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Make a concise poetic statement that describes the vibe of this image.",
                        },
                        {"type": "image_url", "image_url": {"url": res.url}},
                    ],
                },
            ],
        )
        return str(completion.choices[0].message.content).strip()
    except Exception as e:
        return f"Could not process image: {e}"


async def generate_image_caption(image_path: str) -> str:
    """Generate a poetic image caption for a local image."""
    try:
        encoded_image = encode_image(image_path)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You describe images briefly and clearly.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Make a concise poetic statement that describes the vibe of this image.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded_image}"
                            },
                        },
                    ],
                },
            ],
        )
        return str(completion.choices[0].message.content).strip()
    except Exception as e:
        return f"Could not process image: {e}"


# --- API Helpers for Image and Text Generation --- #


async def fetch_pexel_images(query: str, count: int = 6) -> List[str]:
    """Fetch image URLs from the Pexels API matching the provided query."""
    params = {"query": query, "per_page": count}
    headers = {"Authorization": PEXEL_API_KEY}

    response = requests.get(
        "https://api.pexels.com/v1/search",
        headers=headers,
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    return [photo["src"]["portrait"] for photo in data.get("photos", [])]


async def generate_text_snippets(title: str, count: int = 3) -> List[str]:
    """Generate aesthetic text snippets based on a theme."""
    prompt = (
        f"Generate {count} short, aesthetic text snippets inspired by the theme '{title}'. "
        "Each one should be 5-10 words max, evocative and abstract. "
        "Do not use numbering. Write them on separate lines."
    )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    raw_output = str(completion.choices[0].message.content).strip()
    snippets = [line.strip("- ") for line in raw_output.split("\n") if line.strip()]
    return snippets[:count]


async def generate_captions_batch(title: str, count: int) -> List[str]:
    """Generate multiple poetic captions based on a title in one prompt."""
    prompt = (
        f"Generate {count} short, poetic, non-rhyming phrases for the title: '{title}'. "
        "Each phrase should be on its own line. Avoid numbering."
    )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
    )
    captions = str(completion.choices[0].message.content).strip().split("\n")
    return [cap.strip() for cap in captions if cap.strip()]
