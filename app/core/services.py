import os
import sys
import base64
import logging
import json
import asyncio
from typing import List
import requests
from openai import OpenAI, RateLimitError

# Environment
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=0)
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
async def redis_cluster_embeddings(redis, board_id: int):   
    await redis.enqueue_job("cluster_embeddings", board_id=board_id)

async def redis_generate_embedding(redis, item_id: int, content: str, board_id: int):
    await redis.enqueue_job("generate_embedding", item_id, content, board_id)

async def redis_process_image_item(redis, item_id: int, image_url: str, board_id: int):
    await redis.enqueue_job("process_image_item", item_id, image_url, board_id)


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


async def generate_image_data(url: str) -> tuple[str, str, list[float]]:
    """
    Generate description, poetic caption, and embedding for an image URL.
    Handles rate limits with retries.
    """
    for attempt in range(5):  # try up to 5 times
        try:
            # Determine if the image is a URL or a local file path
            if url.startswith(("http://", "https://")):
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                img_bytes = response.content
            else:
                # Local file path case
                with open(url, "rb") as img_file:
                    img_bytes = img_file.read()

            # Convert to Base64 data URI
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            data_url = f"data:image/jpeg;base64,{img_b64}"

            # call responses API with image + prompt
            response = client.responses.create(
                model="gpt-4.1-nano",
                input=[
                    {
                        "role": "system",
                        "content": "You describe images briefly and clearly.",
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "\n1. Provide a description of the scene (1-2 sentences)."
                                "2. A short poetic caption based on this image's vibe. Avoid 'silence' or 'whispers' in the caption. (5–7 words).\n"
                                "\nReturn the response in JSON format with 'description' and 'caption' keys.",
                            },
                            {"type": "input_image", "image_url": data_url},
                        ],
                    },
                ],
            )
            raw_content = response.output[0].content[0].text.strip()
            if raw_content.startswith("```"):
                raw_content = raw_content[
                    raw_content.find("{") : raw_content.rfind("}") + 1
                ]  # grab only inner JSON
            data = json.loads(raw_content)

            description = data["description"]
            caption = data["caption"]
            embedding = await get_text_embedding(description)

            return description, caption, embedding

        except RateLimitError as e:
            wait_time = 2**attempt  # exponential backoff: 1s, 2s, 4s, 8s...
            print(f"⚠️ Rate limit for image data, retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
        except Exception as e:
            raise RuntimeError(f"Failed to generate image data quickly: {e}")

    raise RuntimeError("Exceeded retry attempts for generate_image_data")


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
                        "Respond 'unsafe' if the image contains any sexually explicit or otherwise inappropriate content, "
                        "or 'safe' otherwise."
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
                            "text": "Provide a short poetic caption (7 words max).",
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
        "Each one should be 5-10 words max, evocative and abstract. They should never be sexual in nature. "
        "Do not use numbering. Write them on separate lines."
    )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    raw_output = str(completion.choices[0].message.content).strip()
    snippets = [line.strip("- ") for line in raw_output.split("\n") if line.strip()]
    return snippets[:count]
