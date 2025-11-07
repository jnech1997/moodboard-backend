from app.db.base import Base
from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint

class ClusterLabel(Base):
    __tablename__ = "cluster_labels"

    id = Column(Integer, primary_key=True, index=True)
    board_id = Column(Integer, ForeignKey("boards.id"), nullable=False)
    cluster_id = Column(Integer, nullable=False)
    label = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("board_id", "cluster_id", name="uq_board_cluster"),
    )