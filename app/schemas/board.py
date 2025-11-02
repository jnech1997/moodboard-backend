from typing import List, Optional
from pydantic import BaseModel

class PreviewItem(BaseModel):
    id: int
    image_url: Optional[str] = None
    type: str

class BoardCreate(BaseModel):
    title: str

class BoardPreview(BaseModel):
    id: int
    title: str
    preview_items: List[PreviewItem]

    class Config:
        from_attributes = True

class BoardRead(BaseModel):
    id: int
    title: str
    items: List[PreviewItem]

    class Config:
        from_attributes = True
