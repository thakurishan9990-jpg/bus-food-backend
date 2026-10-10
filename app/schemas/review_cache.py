from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReviewCacheRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dhaba_id: int
    rating: float
    total_reviews: int
    ai_summary: str
    fetched_at: datetime
