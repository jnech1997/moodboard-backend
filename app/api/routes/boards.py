import logging
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from arq import create_pool
from arq.connections import RedisSettings

from app.db.session import get_db
from app.db.models.board import Board
from app.db.models.item import Item
from app.db.models.cluster_label import ClusterLabel
from app.schemas.board import BoardPreview
from app.schemas.cluster import ClusterGroup, ClusterTriggerResponse
from app.core.services import (
    check_text_safe,
    fetch_pexel_images,
    generate_text_snippets,
    generate_captions_batch,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/boards", tags=["boards"])


@router.post("/", response_model=BoardPreview)
async def generate_board(
    board: dict,
    db: AsyncSession = Depends(get_db),
):
    """Generate a new board with mixed content, optimized for speed."""
    title = board.get("title")

    if not title:
        db_board = Board(title="Untitled Board")
        db.add(db_board)
        await db.commit()
        await db.refresh(db_board)
        return {
            "id": db_board.id,
            "title": db_board.title,
            "preview_items": [],
        }

    # Moderation check
    if not await check_text_safe(title):
        logger.info(f"Moderation: flagged for text='{title}...'")
        raise HTTPException(status_code=400, detail="Text violates content policy.")

    # Create the board
    db_board = Board(title=title)
    db.add(db_board)
    await db.commit()
    await db.refresh(db_board)

    try:
        # Fetch images + generate text concurrently
        images_task = fetch_pexel_images(query=title, count=10)
        texts_task = generate_text_snippets(title=title, count=5)
        images, texts = await asyncio.gather(images_task, texts_task)

        # Generate image captions in batch (faster)
        captions = await generate_captions_batch(title, count=10)

        # Create items in batch
        items = [
            Item(type="image", board_id=db_board.id, image_url=img, content=cap)
            for img, cap in zip(images, captions)
        ] + [Item(type="text", board_id=db_board.id, content=txt) for txt in texts]
        db.add_all(items)
        await db.commit()

        for item in items:
            await db.refresh(item)

        # Batch enqueue embedding tasks
        redis = await create_pool(RedisSettings(host="redis", port=6379))
        await asyncio.gather(
            *[
                redis.enqueue_job(
                    "generate_embedding", item.id, item.content, db_board.id
                )
                for item in items
            ]
        )

        # Build preview from first few items
        previews = [
            {"id": item.id, "image_url": item.image_url, "type": item.type}
            for item in items
            if bool(item.image_url)
        ][:6]

    except Exception as e:
        logger.error("Board generation failed:", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "id": db_board.id,
        "title": db_board.title,
        "preview_items": previews,
    }


@router.get("/{board_id}", response_model=BoardPreview)
async def get_board(
    board_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Fetch board by ID along with preview items."""
    result = await db.execute(
        select(Board).where(Board.id == board_id).options(selectinload(Board.items))
    )
    board = result.scalar_one_or_none()

    if not board:
        raise HTTPException(status_code=404, detail="Board not found")

    # Prepare up to 6 preview items
    items = sorted(board.items, key=lambda i: i.id, reverse=True)
    previews = [
        {"id": i.id, "image_url": i.image_url, "type": i.type}
        for i in items
        if i.image_url and i.embedding is not None
    ][:6]

    return {
        "id": board.id,
        "title": board.title,
        "preview_items": previews,
    }


@router.post("/{board_id}/cluster", response_model=ClusterTriggerResponse)
async def cluster_board(board_id: int):
    """Trigger clustering for all items in this board."""
    redis = await create_pool(RedisSettings(host="redis", port=6379))
    await redis.enqueue_job("cluster_embeddings", board_id=board_id)
    return {"cluster_message": "Clustering job enqueued"}


@router.get("/", response_model=list[BoardPreview])
async def list_boards(db: AsyncSession = Depends(get_db)):
    """List all boards with previews of items."""
    result = await db.execute(
        select(Board)
        .options(selectinload(Board.items))
        .order_by(Board.created_at.desc())
    )
    boards = result.scalars().all()

    response = []
    for board in boards:
        items = sorted(board.items, key=lambda i: i.id, reverse=True)
        previews = [
            {"id": i.id, "image_url": i.image_url, "type": i.type}
            for i in items
            if i.image_url and i.embedding is not None
        ][:6]

        response.append(
            {
                "id": board.id,
                "title": board.title,
                "preview_items": previews,
            }
        )

    return response


@router.patch("/{board_id}", response_model=BoardPreview)
async def update_board_title(
    board_id: int,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    title = data.get("title")

    if not title:
        raise HTTPException(status_code=422, detail="Title is required")

    result = await db.execute(select(Board).where(Board.id == board_id))
    board = result.scalar_one_or_none()

    if not board:
        raise HTTPException(status_code=404, detail="Board not found")

    board.title = title
    await db.commit()
    await db.refresh(board)

    return {
        "id": board.id,
        "title": board.title,
        "preview_items": [],
    }


@router.get("/{board_id}/clusters", response_model=list[ClusterGroup])
async def list_clusters(
    board_id: int,
    db: AsyncSession = Depends(get_db),
):
    """List all clusters for items in this board."""
    result = await db.execute(
        select(Item).where((Item.board_id == board_id) & (Item.embedding.isnot(None)))
    )
    items = result.scalars().all()

    label_result = await db.execute(select(ClusterLabel))
    labels = {c.cluster_id: c.label for c in label_result.scalars().all()}

    return [
        {
            "cluster_id": cid,
            "label": labels.get(cid),
            "items": [
                {"id": i.id, "content": i.content, "image_url": i.image_url}
                for i in items
                if bool(i.cluster_id == cid)
            ],
        }
        for cid in sorted({i.cluster_id for i in items if i.cluster_id is not None})
    ]


@router.delete("/{board_id}")
async def delete_board(
    board_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a board along with its items."""
    result = await db.execute(select(Board).where(Board.id == board_id))
    board = result.scalar_one_or_none()

    if not board:
        raise HTTPException(status_code=404, detail="Board not found")

    # Delete all items linked to this board
    await db.execute(delete(Item).where(Item.board_id == board_id))

    # Delete the board itself
    await db.delete(board)
    await db.commit()

    return {"message": f"Board {board_id} deleted"}
