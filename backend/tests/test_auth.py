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
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

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

    async def test_refresh_token_success(self, authenticated_client):
        """Test successful token refresh."""
        client = authenticated_client["client"]
        refresh_token = authenticated_client["tokens"]["refresh_token"]

        response = await client.post(
            "/api/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Test refresh with invalid token."""
        response = await client.post(
            "/api/auth/refresh", json={"refresh_token": "invalid-token"}
        )
        assert response.status_code == 401
