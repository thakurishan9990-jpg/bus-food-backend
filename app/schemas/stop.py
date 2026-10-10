from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StopBase(BaseModel):
    name: str
    lat: float
    lng: float
    sequence_order: int
    minutes_from_origin: int
    halt_duration_minutes: int


class StopCreate(StopBase):
    route_id: int


class StopUpdate(BaseModel):
    name: str | None = None
    lat: float | None = None
    lng: float | None = None
    sequence_order: int | None = None
    minutes_from_origin: int | None = None
    halt_duration_minutes: int | None = None


class StopRead(StopBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: int


class UpcomingStop(StopRead):
    """A stop still ahead of the bus, with its computed ETA."""

    eta: datetime
    minutes_until_arrival: int
