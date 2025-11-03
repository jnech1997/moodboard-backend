import logging
import os
import shutil
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    status,
    Request
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models.item import Item
from app.db.models.board import Board
from app.schemas.item import ItemCreate, ItemRead
from app.core.services import (
    get_text_embedding,
    check_text_safe,
    check_image_safe,
    check_image_safe_url,
    generate_image_caption_url,
    generate_image_caption,
    redis_generate_embedding,
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/boards/{board_id}/items", tags=["items"])


@router.post("/", response_model=ItemRead)
async def add_item(
    request: Request,
    board_id: int,
    item: ItemCreate,  # We'll extend this model
    db: AsyncSession = Depends(get_db),
):
    # Validate the board exists
    result = await db.execute(select(Board).where(Board.id == board_id))
    board = result.scalar_one_or_none()
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")

    # Clone item if source_item_id is provided
    if item.source_item_id:
        original = await db.get(Item, item.source_item_id)
        if not original:
            raise HTTPException(404, detail="Original item not found")

        cloned_item = Item(
            board_id=board_id,
            type=original.type,
            content=original.content,
            image_url=original.image_url,
            embedding=original.embedding,  # shortcut: reuse embedding
        )
        db.add(cloned_item)
        await db.commit()
        await db.refresh(cloned_item)
        return cloned_item

    # Otherwise, process like new item...
    if item.type == "text":
        if not await check_text_safe(item.content):
            raise HTTPException(status_code=400, detail="Text violates content policy.")
        content = item.content
        image_url = None
    else:
        if not await check_image_safe_url(item.image_url):
            raise HTTPException(
                status_code=400, detail="Image violates content policy."
            )
        image_url = item.image_url
        content = await generate_image_caption_url(item.image_url)

    new_item = Item(
        board_id=board_id, type=item.type, content=content, image_url=image_url
    )
    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)

    redis = request.app.state.redis
    await redis_generate_embedding(redis, new_item.id, content, board_id)

    return new_item


@router.get("/", response_model=List[ItemRead])
async def list_items(
    board_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Item).where(Item.board_id == board_id))
    items = result.scalars().all()
    return [
        {
            "id": i.id,
            "content": i.content,
            "image_url": i.image_url,
            "type": i.type,
            "board_id": board_id,
            "embedding": i.embedding,
        }
        for i in items
    ]


@router.post("/upload", response_model=dict)
async def upload_item_image(
    board_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not str(file.content_type).startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Only image uploads are supported.",
        )

    filename = f"{board_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    # Save temporarily
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Moderation check
    is_safe = await check_image_safe(file_path)
    if not is_safe:
        logger.info(f"Moderation: flagged for image='{file.filename}'")
        os.remove(file_path)
        raise HTTPException(
            status_code=400,
            detail="Inappropriate image content.",
        )

    # Caption generation
    caption = await generate_image_caption(file_path)

    # Embedding from caption
    embedding = await get_text_embedding(caption)

    # Save in DB
    image_url = f"/static/{filename}"
    item = Item(
        board_id=board_id,
        type="image",
        image_url=image_url,
        content=caption,
        embedding=embedding,
    )

    db.add(item)
    await db.commit()
    await db.refresh(item)

    return {
        "id": item.id,
        "image_url": image_url,
        "caption": caption,
    }


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    board_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
):
    # Check item exists and belongs to this board
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.board_id == board_id)
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    await db.delete(item)
    await db.commit()

    return {"message": f"Item {item_id} deleted"}
