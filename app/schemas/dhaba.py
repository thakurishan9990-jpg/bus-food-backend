from pydantic import BaseModel, ConfigDict, Field

from app.models.dhaba import DhabaStatus


class DhabaBase(BaseModel):
    name: str
    avg_prep_time_minutes: int = Field(gt=0)
    status: DhabaStatus = DhabaStatus.ACTIVE
    slug: str | None = None
    cuisine: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int = Field(default=0, ge=0)
    avg_bill_inr: int | None = Field(default=None, ge=0)
    review_summary: str | None = None
    commission_pct: int = Field(default=12, ge=0, le=100)
    sponsored_offer: str | None = None


class DhabaCreate(DhabaBase):
    stop_id: int
    google_place_id: str | None = None


class DhabaUpdate(BaseModel):
    name: str | None = None
    avg_prep_time_minutes: int | None = Field(default=None, gt=0)
    status: DhabaStatus | None = None
    google_place_id: str | None = None
    slug: str | None = None
    cuisine: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    avg_bill_inr: int | None = Field(default=None, ge=0)
    review_summary: str | None = None
    commission_pct: int | None = Field(default=None, ge=0, le=100)
    sponsored_offer: str | None = None


class DhabaRead(DhabaBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stop_id: int
    google_place_id: str | None
    is_pure_veg: bool


class MenuItemBase(BaseModel):
    name: str
    price_inr: int = Field(gt=0)
    is_veg: bool
    is_available: bool = True
    dish_id: str | None = None
    description: str | None = None
    image_url: str | None = None
    is_signature: bool = False


class MenuItemCreate(MenuItemBase):
    dhaba_id: int


class MenuItemUpdate(BaseModel):
    name: str | None = None
    price_inr: int | None = Field(default=None, gt=0)
    is_veg: bool | None = None
    is_available: bool | None = None
    dish_id: str | None = None
    description: str | None = None
    image_url: str | None = None
    is_signature: bool | None = None


class MenuItemRead(MenuItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dhaba_id: int
