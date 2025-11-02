from pydantic import BaseModel

class SystemStats(BaseModel):
    boards: int
    items: int
    clusters: int
    labels: int