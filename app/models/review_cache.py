from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReviewCache(Base):
    __tablename__ = "review_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    dhaba_id: Mapped[int] = mapped_column(ForeignKey("dhabas.id", ondelete="CASCADE"), unique=True)
    rating: Mapped[float] = mapped_column(Float)
    total_reviews: Mapped[int] = mapped_column(Integer)
    raw_reviews: Mapped[list | dict] = mapped_column(JSON)
    ai_summary: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    dhaba: Mapped["Dhaba"] = relationship(back_populates="review_cache")
