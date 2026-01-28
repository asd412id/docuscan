import pytest
import asyncio
import os
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DEBUG"] = "false"
os.environ["REDIS_ENABLED"] = "false"
os.environ["CELERY_ENABLED"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "false"

from app.main import app
from app.database import Base, get_db
from app.utils.security import generate_csrf_token, CSRF_COOKIE_NAME, CSRF_HEADER_NAME


# Test database engine
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

test_session_maker = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for session scope."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_database():
    """Create tables before each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def csrf_token() -> str:
    """Generate a CSRF token for tests."""
    return generate_csrf_token()


@pytest.fixture
async def client(csrf_token: str) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with CSRF token."""
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={CSRF_COOKIE_NAME: csrf_token},
    ) as ac:
        # Store CSRF token for use in requests
        ac.csrf_token = csrf_token
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create database session for tests."""
    async with test_session_maker() as session:
        yield session


@pytest.fixture
async def authenticated_client(client: AsyncClient) -> AsyncGenerator[dict, None]:
    """Create authenticated client with test user."""
    # Register user
    register_data = {
        "email": "test@example.com",
        "username": "testuser",
        "password": "testpassword123",
        "full_name": "Test User",
    }
    await client.post("/api/auth/register", json=register_data)

    # Login
    login_data = {"username": "testuser", "password": "testpassword123"}
    response = await client.post(
        "/api/auth/token",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    tokens = response.json()

    # Include CSRF token in headers for state-changing requests
    csrf_token = getattr(client, "csrf_token", generate_csrf_token())

    yield {
        "client": client,
        "tokens": tokens,
        "headers": {
            "Authorization": f"Bearer {tokens['access_token']}",
            CSRF_HEADER_NAME: csrf_token,
        },
        "csrf_token": csrf_token,
    }
