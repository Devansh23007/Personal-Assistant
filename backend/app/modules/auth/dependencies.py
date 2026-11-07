from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import JWT_ALGORITHM
from app.modules.auth.models import User
from app.modules.auth.service import get_user_by_email

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[JWT_ALGORITHM])
        email = payload.get("sub")
        if not isinstance(email, str):
            raise unauthorized
    except InvalidTokenError:
        raise unauthorized from None

    user = get_user_by_email(db, email)
    if user is None:
        raise unauthorized
    return user
