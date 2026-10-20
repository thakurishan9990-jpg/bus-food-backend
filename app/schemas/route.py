from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RouteBase(BaseModel):
    name: str
    origin: str
    destination: str
    code: str | None = None
    slug: str | None = None
    highway: str | None = None
    operator: str | None = None
    duration: str | None = None


class RouteCreate(RouteBase):
    pass


class RouteUpdate(BaseModel):
    name: str | None = None
    origin: str | None = None
    destination: str | None = None
    code: str | None = None
    slug: str | None = None
    highway: str | None = None
    operator: str | None = None
    duration: str | None = None


class RouteRead(RouteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
