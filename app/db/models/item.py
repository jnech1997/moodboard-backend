from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base
from pgvector.sqlalchemy import Vector

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    board_id = Column(Integer, ForeignKey("boards.id", ondelete="CASCADE"))
    type = Column(String, default="text")  # "text" or "image"
    content = Column(String, nullable=False)
    image_url = Column(String, nullable=True)  # 🔹 new
    embedding = Column(Vector(1536))
    cluster_id = Column(Integer, nullable=True)

    board = relationship("Board", back_populates="items")