from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode(), bcrypt.gensalt()
    ).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: UUID) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expire_minutes
    )
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> UUID:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return UUID(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise ValueError("Invalid token") from exc
