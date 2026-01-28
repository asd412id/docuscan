"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient


class TestAuthRegister:
    """Test user registration."""

    async def test_register_success(self, client: AsyncClient):
        """Test successful user registration."""
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "newuser@example.com",
                "username": "newuser",
                "password": "securepassword123",
                "full_name": "New User",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["username"] == "newuser"
        assert "id" in data

    async def test_register_duplicate_email(self, client: AsyncClient):
        """Test registration with duplicate email."""
        user_data = {
            "email": "duplicate@example.com",
            "username": "user1",
            "password": "password123",
        }
        await client.post("/api/auth/register", json=user_data)

        user_data["username"] = "user2"
        response = await client.post("/api/auth/register", json=user_data)
        assert response.status_code == 400

    async def test_register_duplicate_username(self, client: AsyncClient):
        """Test registration with duplicate username."""
        user_data = {
            "email": "user1@example.com",
            "username": "duplicateuser",
            "password": "password123",
        }
        await client.post("/api/auth/register", json=user_data)

        user_data["email"] = "user2@example.com"
        response = await client.post("/api/auth/register", json=user_data)
        assert response.status_code == 400

    async def test_register_invalid_email(self, client: AsyncClient):
        """Test registration with invalid email."""
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "invalid-email",
                "username": "testuser",
                "password": "password123",
            },
        )
        assert response.status_code == 422


class TestAuthLogin:
    """Test user login."""

    async def test_login_success(self, client: AsyncClient):
        """Test successful login."""
        # Register first
        await client.post(
            "/api/auth/register",
            json={
                "email": "login@example.com",
                "username": "loginuser",
                "password": "password123",
            },
        )

        # Login
        response = await client.post(
            "/api/auth/token",
            data={"username": "loginuser", "password": "password123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        # refresh_token is no longer in JSON response (security fix)
        # It's now sent via httpOnly cookie
        assert "refresh_token" not in data
        # Check that refresh_token cookie was set
        assert "refresh_token" in response.cookies

    async def test_login_invalid_password(self, client: AsyncClient):
        """Test login with invalid password."""
        await client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "password123",
            },
        )

        response = await client.post(
            "/api/auth/token",
            data={"username": "testuser", "password": "wrongpassword"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with nonexistent user."""
        response = await client.post(
            "/api/auth/token",
            data={"username": "nonexistent", "password": "password123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 401


class TestAuthMe:
    """Test current user endpoint."""

    async def test_me_authenticated(self, authenticated_client):
        """Test getting current user when authenticated."""
        client = authenticated_client["client"]
        headers = authenticated_client["headers"]

        response = await client.get("/api/auth/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["email"] == "test@example.com"

    async def test_me_unauthenticated(self, client: AsyncClient):
        """Test getting current user without authentication."""
        response = await client.get("/api/auth/me")
        assert response.status_code == 401


class TestAuthRefresh:
    """Test token refresh."""

    async def test_refresh_token_success(self, client: AsyncClient):
        """Test successful token refresh using httpOnly cookie."""
        # Register user
        await client.post(
            "/api/auth/register",
            json={
                "email": "refresh@example.com",
                "username": "refreshuser",
                "password": "password123",
            },
        )

        # Login to get refresh token cookie
        login_response = await client.post(
            "/api/auth/token",
            data={"username": "refreshuser", "password": "password123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert login_response.status_code == 200

        # Extract refresh token cookie
        refresh_token = login_response.cookies.get("refresh_token")
        assert refresh_token is not None, "refresh_token cookie should be set"

        # Use refresh token to get new access token
        # Pass the cookie explicitly since httpx with ASGITransport may not persist it
        response = await client.post(
            "/api/auth/refresh",
            cookies={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        # New refresh token is also set via cookie, not in JSON
        assert "refresh_token" not in data

    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Test refresh with invalid token."""
        response = await client.post(
            "/api/auth/refresh", json={"refresh_token": "invalid-token"}
        )
        assert response.status_code == 401
