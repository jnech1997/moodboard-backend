from fastapi import APIRouter, Depends, Request
from fastapi.openapi.utils import get_openapi
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.system import SystemStats

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/stats", response_model=SystemStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Return system-wide statistics."""
    sql = text("""
        SELECT
            (SELECT COUNT(*) FROM boards) AS boards,
            (SELECT COUNT(*) FROM items) AS items,
            (SELECT COUNT(DISTINCT cluster_id) FROM items WHERE cluster_id IS NOT NULL) AS clusters,
            (SELECT COUNT(*) FROM cluster_labels) AS labels
    """)
    result = await db.execute(sql)
    return result.mappings().first()


@router.get("/docs.json", include_in_schema=False)
async def get_openapi_json(request: Request):
    """Return the full OpenAPI schema in JSON format."""
    app = request.app
    return get_openapi(
        title="Moodboard API",
        version="1.0.0",
        description="Full OpenAPI specification for the Moodboard backend.",
        routes=app.routes,
    )
