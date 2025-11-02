from typing import Optional, Literal, Union, List
from pydantic import BaseModel

class TextItemCreate(BaseModel):
    type: Literal["text"]
    content: str
    source_item_id: Optional[int] = None

class ImageItemCreate(BaseModel):
    type: Literal["image"]
    image_url: str
    source_item_id: Optional[int] = None

ItemCreate = Union[TextItemCreate, ImageItemCreate]

class ItemRead(BaseModel):
    id: int
    board_id: int
    type: Literal["text", "image"]
    content: Optional[str] = None
    image_url: Optional[str] = None
    cluster_id: Optional[int] = None
    similarity: Optional[float] = None  # for search
    embedding: Optional[List[float]] = None  # probably omit in default responses

    class Config:
        from_attributes = True
