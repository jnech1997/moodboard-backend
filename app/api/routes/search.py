from fastapi import APIRouter, Query, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.services import get_text_embedding
from app.schemas.search import SearchResult

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("/", response_model=list[SearchResult])
async def search_items(
    q: str = Query(..., description="Search query"),
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Search items based on semantic similarity to the query."""

    # Get query embedding
    query_emb = await get_text_embedding(q)

    # Perform similarity search using PostgreSQL <=> operator
    sql = text("""
        SELECT id, board_id, content, image_url, type,
               1 - (embedding <=> (:query_emb)::vector) AS similarity
        FROM items
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> (:query_emb)::vector
        LIMIT :limit
    """)

    rows = await db.execute(sql, {"query_emb": str(query_emb), "limit": limit})
    results = rows.mappings().all()

    return [
        {
            "id": r["id"],
            "board_id": r["board_id"],
            "content": r["content"],
            "image_url": r["image_url"],
            "type": r["type"],
            "similarity": round(r["similarity"], 10),
        }
        for r in results
    ]
