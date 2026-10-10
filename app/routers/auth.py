from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import SignupRequest, TokenResponse
from app.utils.auth import create_access_token, hash_password, verify_password
from app.utils.errors import ConflictError, UnauthorizedError

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_token(user: User) -> TokenResponse:
    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return TokenResponse(access_token=token, user=user)


@router.post("/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Create a new passenger account and return an access token.

    Public signup always creates role=passenger; dhaba/admin accounts are seeded
    or created by an admin, never through this endpoint.
    """
    if db.query(User).filter(User.phone == payload.phone).first() is not None:
        raise ConflictError("An account with this phone number already exists")

    user = User(
        phone=payload.phone,
        name=payload.name,
        hashed_password=hash_password(payload.password),
        role=UserRole.PASSENGER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_token(user)


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenResponse:
    """Log in with phone number (as the 'username' field) and password.

    Uses OAuth2PasswordRequestForm so Swagger's Authorize popup can log in directly.
    """
    user = db.query(User).filter(User.phone == form_data.username).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise UnauthorizedError("Incorrect phone number or password")
    return _issue_token(user)
