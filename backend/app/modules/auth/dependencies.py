from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import JWT_ALGORITHM
from app.modules.auth.models import User
from app.modules.auth.service import get_user_by_email

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

DEFAULT_LOCAL_EMAIL = "devansh@local"


def get_or_create_default_user(db: Session) -> User:
    user = get_user_by_email(db, DEFAULT_LOCAL_EMAIL)
    if not user:
        user = User(
            email=DEFAULT_LOCAL_EMAIL,
            password_hash="local_development_password",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if token:
        try:
            payload = jwt.decode(token, settings.app_secret_key, algorithms=[JWT_ALGORITHM])
            email = payload.get("sub")
            if isinstance(email, str):
                user = get_user_by_email(db, email)
                if user is not None:
                    return user
        except InvalidTokenError:
            pass

    # No token or invalid token: automatically grant access as the default local owner
    return get_or_create_default_user(db)
