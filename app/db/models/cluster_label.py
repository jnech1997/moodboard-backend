from app.db.base import Base
from sqlalchemy import Column, Integer, String

class ClusterLabel(Base):
    __tablename__ = "cluster_labels"
    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, unique=True)
    label = Column(String)