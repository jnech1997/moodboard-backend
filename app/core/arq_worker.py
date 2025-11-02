import asyncio
import logging
import os
import sys
from typing import cast

from pgvector.sqlalchemy import Vector
from arq.connections import RedisSettings

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

from sklearn.cluster import KMeans

from openai import AsyncOpenAI

from app.db.session import async_session
from app.db.models import Item
from app.db.models.cluster_label import ClusterLabel
from app.core.services import get_text_embedding

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
    embedding = await get_text_embedding(content)

    async with async_session() as db:
        item = await db.get(Item, item_id)
        if not item:
            logger.info(f"⚠️ Item {item_id} not found")
            return

        item.embedding = cast(Vector, embedding)  # type: ignore
        await db.commit()
        logger.info(f"✅ Stored embedding for item {item_id}")


async def cluster_embeddings(ctx, board_id: int):
    """Cluster items for a board based on their embeddings and label the clusters."""
    lock_key = "cluster_lock"
    redis = ctx["redis"]

    # Acquire lock to prevent concurrent clustering
    if not await redis.setnx(lock_key, "1"):
        logger.warning("⚠️ Clustering already running. Skipping.")
        return
    await redis.expire(lock_key, 300)

    try:
        logger.info("🔹 Starting clustering job...")

        # Retrieve items with embeddings
        async with async_session() as db:
            async with db.begin():
                result = await db.execute(
                    select(Item).where(
                        Item.board_id == board_id,
                        Item.embedding.isnot(None),
                    )
                )
                items = result.scalars().all()
                if not items:
                    logger.warning("No items found to cluster.")
                    return

                embeddings = [i.embedding for i in items]
                n_clusters = min(5, len(embeddings))

                # Perform KMeans clustering
                kmeans = KMeans(n_clusters=n_clusters, n_init=10)
                labels = kmeans.fit_predict(embeddings)  # type: ignore

                for item, cluster_id in zip(items, labels):
                    item.cluster_id = int(cluster_id)  # type: ignore
                logger.info(f"✅ Assigned cluster IDs for {len(items)} items.")

                # Delete old cluster labels
                await db.execute(delete(ClusterLabel))

        # Generate descriptive labels for each cluster
        async with async_session() as db:
            statements = []

            for cluster_id in range(n_clusters):
                contents = [i.content for i in items if bool(i.cluster_id == cluster_id)]
                sample_text = ", ".join(contents[:3]) # type: ignore
                prompt = f"Name this group of items: {sample_text}"

                completion = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You name clusters of similar text. Be descriptive and "
                                "come up with a title that's not just Cluster 0, Cluster 1, etc. "
                                "Don't return the title in quotes."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                )
                label_name = str(completion.choices[0].message.content).strip()
                logger.info(f"💬 Cluster {cluster_id}: {label_name}")

                statements.append(
                    insert(ClusterLabel)
                    .values(cluster_id=cluster_id, label=label_name)
                    .on_conflict_do_update(
                        index_elements=[ClusterLabel.cluster_id],
                        set_={"label": label_name},
                    )
                )

            # Commit all label inserts in a single transaction
            async with db.begin():
                for stmt in statements:
                    await db.execute(stmt)

            logger.info("✅ All cluster labels committed in one transaction.")

    except Exception as e:
        logger.error(f"❌ Clustering failed: {e}", exc_info=True)

    finally:
        # Ensure the lock is always released
        await redis.delete(lock_key)
        await asyncio.sleep(0.1)  # Slight delay to ensure lock is cleared


# Retry behavior for clustering jobs
cluster_embeddings.max_tries = 3
cluster_embeddings.retry_delay = 10  # seconds


class WorkerSettings:
    """ARQ worker configuration."""

    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL"))
    functions = [generate_embedding, cluster_embeddings]
    keep_result = 0
