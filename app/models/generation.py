from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Generation(Base):
    __tablename__ = "generations"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    env = Column(String, nullable=False)
    artifact_key = Column(String, nullable=False)
    lint_status = Column(String, nullable=False)
    lint_report = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=_utcnow)
