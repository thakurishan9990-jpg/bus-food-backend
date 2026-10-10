from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DhabaBase(BaseModel):
    name: str
    avg_prep_time_minutes: int = Field(gt=0)
    is_active: bool = True


class DhabaCreate(DhabaBase):
    stop_id: int
    google_place_id: str | None = None


class DhabaUpdate(BaseModel):
    name: str | None = None
    avg_prep_time_minutes: int | None = Field(default=None, gt=0)
    is_active: bool | None = None
    google_place_id: str | None = None


class DhabaRead(DhabaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stop_id: int
    google_place_id: str | None


class DhabaWithReviews(DhabaRead):
    """Dhaba enriched with Google rating + AI summary for the passenger-facing listing."""

    rating: float | None = None
    total_reviews: int | None = None
    ai_summary: str | None = None


class MenuItemBase(BaseModel):
    name: str
    price: Decimal = Field(gt=0)
    is_veg: bool


class MenuItemCreate(MenuItemBase):
    dhaba_id: int


class MenuItemUpdate(BaseModel):
    name: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    is_veg: bool | None = None


class MenuItemRead(MenuItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dhaba_id: int
