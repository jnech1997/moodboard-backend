from pydantic import BaseModel
from typing import Optional, Literal

class SearchResult(BaseModel):
    id: int
    board_id: int
    content: Optional[str] = None
    image_url: Optional[str] = None
    type: Literal["text", "image"]
    similarity: float

    class Config:
        from_attributes = True
