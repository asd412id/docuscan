from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
import secrets
import logging
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models.models import User


settings = get_settings()
logger = logging.getLogger(__name__)

# Allowed algorithms - explicitly whitelist to prevent algorithm confusion attacks
ALLOWED_ALGORITHMS = ["HS256", "HS384", "HS512"]

# JWT claims validation options
JWT_DECODE_OPTIONS = {
    "verify_signature": True,
    "verify_exp": True,
    "verify_nbf": True,
    "verify_iat": True,
    "require": ["exp", "iat", "sub", "type"],
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    # Add security claims
    to_encode.update(
        {
            "exp": expire,
            "iat": now,
            "nbf": now,
            "type": "access",
            "jti": secrets.token_urlsafe(
                16
            ),  # Unique token ID for potential revocation
        }
    )

    # Validate algorithm is in allowed list
    if settings.algorithm not in ALLOWED_ALGORITHMS:
        raise ValueError(f"Algorithm {settings.algorithm} not allowed")

    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key, algorithm=settings.algorithm
    )
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.refresh_token_expire_days)

    # Add security claims
    to_encode.update(
        {
            "exp": expire,
            "iat": now,
            "nbf": now,
            "type": "refresh",
            "jti": secrets.token_urlsafe(
                16
            ),  # Unique token ID for potential revocation
        }
    )

    # Validate algorithm is in allowed list
    if settings.algorithm not in ALLOWED_ALGORITHMS:
        raise ValueError(f"Algorithm {settings.algorithm} not allowed")

    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key, algorithm=settings.algorithm
    )
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and validate JWT token with security checks.

    Security measures:
    - Validates algorithm is in allowed list (prevents algorithm confusion attacks)
    - Validates signature
    - Validates expiration (exp)
    - Validates not-before (nbf)
    - Validates issued-at (iat)
    - Requires specific claims to be present
    """
    try:
        # Validate algorithm is in allowed list
        if settings.algorithm not in ALLOWED_ALGORITHMS:
            logger.warning(f"Algorithm {settings.algorithm} not in allowed list")
            return None

        # Decode with strict validation
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],  # Only allow configured algorithm
            options=JWT_DECODE_OPTIONS,
        )

        # Additional validation: check token type is present
        if "type" not in payload:
            logger.warning("Token missing type claim")
            return None

        # Validate type is expected value
        if payload.get("type") not in ["access", "refresh"]:
            logger.warning(f"Invalid token type: {payload.get('type')}")
            return None

        return payload
    except JWTError as e:
        logger.debug(f"JWT decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error decoding token: {e}")
        return None


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> Optional[User]:
    user = await get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def create_user(
    db: AsyncSession,
    email: str,
    username: str,
    password: str,
    full_name: Optional[str] = None,
) -> User:
    hashed_password = get_password_hash(password)
    user = User(
        email=email,
        username=username,
        hashed_password=hashed_password,
        full_name=full_name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user
