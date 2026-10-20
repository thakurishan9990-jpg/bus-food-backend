from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.trip import TripStatus


class TripBase(BaseModel):
    operator: str
    bus_number: str
    departure_time: datetime


class TripCreate(TripBase):
    route_id: int
    status: TripStatus = TripStatus.SCHEDULED


class TripUpdate(BaseModel):
    operator: str | None = None
    bus_number: str | None = None
    departure_time: datetime | None = None
    status: TripStatus | None = None


class TripRead(TripBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: int
    bus_id: int | None
    current_delay_minutes: int
    last_passed_stop_id: int | None
    status: TripStatus


class TripDelayUpdate(BaseModel):
    current_delay_minutes: int


class TripLastPassedStopUpdate(BaseModel):
    last_passed_stop_id: int
