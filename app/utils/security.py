from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.utils.auth import decode_access_token
from app.utils.errors import ForbiddenError, UnauthorizedError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Decode the bearer token and load the corresponding User, or raise 401."""
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise UnauthorizedError()

    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedError()
    return user


def require_role(*allowed_roles: UserRole):
    """Dependency factory: only lets through users whose role is in allowed_roles."""

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenError(
                f"This action requires one of roles {[r.value for r in allowed_roles]}, "
                f"but you are '{current_user.role.value}'"
            )
        return current_user

    return checker
