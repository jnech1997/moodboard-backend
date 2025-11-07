import asyncio
import logging
import os
import sys
import time
import random
from typing import cast

from pgvector.sqlalchemy import Vector
from arq import cron, Worker
from arq.connections import RedisSettings

from sqlalchemy import select, delete, update
from sqlalchemy.dialects.postgresql import insert

from sklearn.cluster import KMeans

from openai import AsyncOpenAI, RateLimitError

from app.db.session import async_session
from app.db.models import Item, Board
from app.db.models.cluster_label import ClusterLabel
from app.core.services import get_text_embedding, generate_image_data

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)

# OpenAI client
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def generate_embedding(ctx, item_id: int, content: str, board_id: int):
    """Background job: generate and store embedding for a single item."""
    logger.info(f"🔹 Generating embedding for item {item_id}")

    try: 
        embedding = await get_text_embedding(content)
        async with async_session() as db:
            item = await db.get(Item, item_id)
            if not item:
                logger.info(f"⚠️ Item {item_id} not found")
                return

            item.embedding = cast(Vector, embedding)  # type: ignore
            await db.commit()
            logger.info(f"✅ Stored embedding for item {item_id}")

    except Exception as e:
        logger.error(f"❌ Failed to process text item {item_id}: {e}", exc_info=True)

        async with async_session() as db:
            logger.info(f"🗑️ Deleting failed text item {item_id}")
            await db.delete(await db.get(Item, item_id))
            await db.commit()


MAX_RETRIES = 5

async def process_image_item(ctx, item_id: int, image_url: str, board_id: int):
    """Process image entry: generate description, caption, embedding."""
    logger.info(f"🔹 Processing image item {item_id}")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # May throw RateLimitError or other OpenAI exception
            description, caption, embedding = await generate_image_data(image_url)

            # Store content + embedding
            async with async_session() as db:
                item = await db.get(Item, item_id)
                if not item:
                    logger.warning(f"⚠️ Item {item_id} not found")
                    return

                item.content = caption  # Poetic caption for display
                item.embedding = embedding  # Derived from description
                await db.commit()

            logger.info(f"✅ Stored processed image item {item_id}")
            break  # Exit retry loop once successful

        except RateLimitError as e:
            if attempt < MAX_RETRIES:
                # Exponential backoff with jitter between 1s and ~30s
                backoff = min(2**attempt + random.random(), 30)
                logger.warning(
                    f"⚠️ Rate limited→ retry {attempt}/{MAX_RETRIES} in {backoff:.2f}s for item {item_id}"
                )
                await asyncio.sleep(backoff)
            else:
                logger.error(
                    f"❌ Max retries reached for item {item_id}: {e}", exc_info=True
                )
                await cleanup_failed_item(item_id)
                return

        except Exception as e:
            logger.error(f"❌ Unexpected error for item {item_id}: {e}", exc_info=True)
            await cleanup_failed_item(item_id)
            return


async def cleanup_failed_item(item_id: int):
    """Helper: delete failed item from DB (idempotent)."""
    async with async_session() as db:
        item = await db.get(Item, item_id)
        if item:
            await db.delete(item)
            await db.commit()
            logger.info(f"🗑️ Removed failed image item {item_id}")
        else:
            logger.warning(f"⚠️ Item {item_id} not found during deletion")



async def cluster_embeddings(ctx, board_id: int):
    """Cluster items for a single board and save the labels."""
    try:
        logger.info(f"🔹 Starting clustering job for board {board_id}...")

        async with async_session() as db:
            await db.execute(update(Board).where(Board.id == board_id).values(is_clustering=True))
            await db.commit()

            # Fetch items with embeddings for this board
            result = await db.execute(
                select(Item).where(
                    Item.board_id == board_id,
                    Item.embedding.isnot(None),
                )
            )
            items = result.scalars().all()
            if not items:
                logger.warning(f"No items found to cluster for board {board_id}.")
                return

            # Prepare embeddings and fit clustering
            embeddings = [i.embedding for i in items]
            n_clusters = min(5, len(embeddings))
            logger.info(
                f"🧠 Clustering {len(items)} items into {n_clusters} clusters for board {board_id}."
            )

            kmeans = KMeans(n_clusters=n_clusters, n_init=10)
            labels = kmeans.fit_predict(embeddings)  # type: ignore

            # Update cluster_id in memory
            for item, cluster_id in zip(items, labels):
                item.cluster_id = int(cluster_id)

            # Clear old labels for this board
            await db.execute(
                delete(ClusterLabel).where(ClusterLabel.board_id == board_id)
            )

            # Apply updated cluster IDs and stage items for commit
            for item in items:
                db.add(item)

            logger.info(f"✅ Updated cluster IDs for board {board_id}.")

            # Label clusters using OpenAI
            statements = []
            for cluster_id in range(n_clusters):
                cluster_items = [i.content for i in items if i.cluster_id == cluster_id]
                preview_text = ", ".join(cluster_items[:3])  # sample text for naming
                prompt = f"Name this group of items: {preview_text}"

                completion = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "Name the topic of this group of items in a descriptive title.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                )
                label_name = str(completion.choices[0].message.content).strip()
                logger.info(
                    f"💬 Cluster {cluster_id} on board {board_id}: {label_name}"
                )

                statements.append(
                    insert(ClusterLabel)
                    .values(cluster_id=cluster_id, board_id=board_id, label=label_name)
                )

            # Execute all label statements
            for stmt in statements:
                await db.execute(stmt)
            
            await db.execute(update(Board).where(Board.id == board_id).values(is_clustering=False))

            # Final commit for everything
            await db.commit()
            logger.info(f"🏁 Clustering complete for board {board_id}.")

    except Exception as e:
        await db.execute(
            update(Board).where(Board.id == board_id).values(is_clustering=False)
        )
        await db.commit()
        logger.error(f"❌ Clustering failed on board {board_id}: {e}", exc_info=True)

    finally:
        await asyncio.sleep(0.1)


# Retry behavior for clustering jobs
cluster_embeddings.max_tries = 3
cluster_embeddings.retry_delay = 10  # seconds

async def worker_heartbeat(ctx):
    redis = ctx["redis"]
    await redis.set(
        "arq:heartbeat", str(time.time()), ex=60
    )  # expire in 60 seconds


async def run_worker_forever():
    """
    Resilient loop that keeps the ARQ worker running.
    Restarts worker on failure with exponential backoff.
    """
    backoff = 1
    while True:
        try:
            worker = Worker(
                functions = [
                    generate_embedding,
                    process_image_item,
                    cluster_embeddings,
                ],
                redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL")),
                cron_jobs = [
                    cron(worker_heartbeat, second=0),
                ],
                keep_result = 0,
                max_jobs = 5,
            )
            logger.info("🚀 Starting ARQ worker...")
            await worker.async_run()
        except asyncio.CancelledError:
            logger.warning("🌀 Worker shutdown triggered by CancelledError — safe to ignore.")
        except Exception as e:
            logger.error(f"❌ Worker crashed: {e}", exc_info=True)
            logger.info(f"🔁 Restarting worker in {backoff} seconds...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)  # Max backoff 1 minute
        else:
            backoff = 1  # Reset backoff on clean exit


if __name__ == "__main__":
    try:
        asyncio.run(run_worker_forever())
    except KeyboardInterrupt:
        logger.info("🛑 Worker manually stopped.")
