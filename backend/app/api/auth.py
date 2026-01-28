from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, Optional
import logging

from app.database import get_db
from app.schemas.schemas import (
    UserCreate,
    UserResponse,
    UserLogin,
    Token,
    RefreshTokenRequest,
    MessageResponse,
)
from app.services.auth_service import (
    authenticate_user,
    create_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_user_by_username,
    get_user_by_email,
    get_user_by_id,
)
from app.models.models import User
from app.utils.rate_limit import limiter
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter()

# Cookie configuration for security
REFRESH_TOKEN_COOKIE_NAME = "refresh_token"
COOKIE_MAX_AGE = settings.refresh_token_expire_days * 24 * 60 * 60  # days to seconds
COOKIE_SECURE = not settings.debug  # Only secure in production
COOKIE_HTTPONLY = True
COOKIE_SAMESITE = (
    "lax"  # "lax" allows top-level navigations, "strict" for maximum security
)


class OAuth2PasswordBearerWithCookie(OAuth2PasswordBearer):
    """
    Custom OAuth2 scheme that also checks for refresh token in cookies.
    This supports both Authorization header (for access token) and cookies (for refresh token).
    """

    async def __call__(self, request: Request) -> Optional[str]:
        # First try to get token from Authorization header
        authorization = request.headers.get("Authorization")
        if authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() == "bearer" and token:
                return token

        # If no Authorization header, this will raise the appropriate error
        return await super().__call__(request)


oauth2_scheme = OAuth2PasswordBearerWithCookie(tokenUrl="/api/auth/token")


def set_refresh_token_cookie(response: Response, refresh_token: str) -> None:
    """Set refresh token as httpOnly secure cookie."""
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        max_age=COOKIE_MAX_AGE,
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/api/auth",  # Only send cookie to auth endpoints
    )


def clear_refresh_token_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        path="/api/auth",
        httponly=COOKIE_HTTPONLY,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
    )


def get_refresh_token_from_cookie(request: Request) -> Optional[str]:
    """Get refresh token from cookie if present."""
    return request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    if payload.get("type") != "access":
        raise credentials_exception

    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception

    user = await get_user_by_username(db, username)
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )

    return user


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit(settings.rate_limit_auth)
async def register(
    request: Request, user_data: UserCreate, db: AsyncSession = Depends(get_db)
):
    """Register a new user."""
    # Check if username exists
    existing_user = await get_user_by_username(db, user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Check if email exists
    existing_email = await get_user_by_email(db, user_data.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Create user
    user = await create_user(
        db,
        email=user_data.email,
        username=user_data.username,
        password=user_data.password,
        full_name=user_data.full_name,
    )

    return user


@router.post("/token", response_model=Token)
@limiter.limit(settings.rate_limit_auth)
async def login(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
):
    """
    Login and get access token.

    Returns access_token in response body and sets refresh_token as httpOnly cookie.
    This provides security against XSS attacks as the refresh token cannot be accessed
    via JavaScript.
    """
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    # Set refresh token as httpOnly cookie (not accessible via JavaScript)
    set_refresh_token_cookie(response, refresh_token)

    # Only return access token in body - refresh token is stored in httpOnly cookie only
    # This prevents XSS attacks from stealing refresh tokens
    return Token(access_token=access_token, token_type="bearer")


@router.post("/refresh", response_model=Token)
@limiter.limit(settings.rate_limit_auth)
async def refresh_token(
    request: Request,
    response: Response,
    token_request: Optional[RefreshTokenRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh access token using refresh token from httpOnly cookie.

    The refresh token is read from the httpOnly cookie (set during login).
    A new access token is returned and a new refresh token is set in the cookie
    (token rotation for security).
    """
    # Get refresh token from httpOnly cookie only (more secure)
    refresh_token_value = get_refresh_token_from_cookie(request)

    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
        )

    payload = decode_token(refresh_token_value)
    if payload is None or payload.get("type") != "refresh":
        # Clear invalid cookie if present
        clear_refresh_token_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    username = payload.get("sub")
    user = await get_user_by_username(db, username)
    if not user or not user.is_active:
        clear_refresh_token_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    access_token = create_access_token(data={"sub": user.username})
    new_refresh_token = create_refresh_token(data={"sub": user.username})

    # Update refresh token cookie with new token (token rotation)
    set_refresh_token_cookie(response, new_refresh_token)

    # Only return access token - new refresh token is in httpOnly cookie only
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get current user information."""
    return current_user


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Logout user.

    Clears the refresh token cookie. The client should also discard
    the access token from memory.
    """
    # Clear the refresh token cookie
    clear_refresh_token_cookie(response)

    logger.info(f"User {current_user.username} logged out")
    return MessageResponse(message="Successfully logged out")
