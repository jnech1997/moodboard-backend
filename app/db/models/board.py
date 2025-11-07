from sqlalchemy import Column, Integer, String, DateTime, Boolean, func
from sqlalchemy.orm import relationship
from app.db.base import Base

class Board(Base):
    __tablename__ = "boards"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_clustering = Column(Boolean, nullable=False, server_default="false")
    items = relationship("Item", back_populates="board", cascade="all, delete-orphan")