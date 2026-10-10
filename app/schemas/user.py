from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRole


class SignupRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=15)
    name: str
    password: str = Field(min_length=6)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    name: str
    role: UserRole
    dhaba_id: int | None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
