from typing import List, Optional
from pydantic import BaseModel

class ClusterLabelBase(BaseModel):
    cluster_id: int
    label: str

class ClusterGroup(BaseModel):
    cluster_id: int
    label: Optional[str]
    items: List["ClusterItem"]

    class Config:
        from_attributes = True

class ClusterItem(BaseModel):
    id: int
    content: Optional[str] = None
    image_url: Optional[str] = None

    class Config:
        from_attributes = True

class ClusterTriggerResponse(BaseModel):
    cluster_message: str
