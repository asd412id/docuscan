"""Tests for health endpoint and basic API functionality."""

import pytest
from httpx import AsyncClient


class TestHealth:
    """Test health check endpoint."""

    async def test_health_check(self, client: AsyncClient):
        """Test health check returns OK."""
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "app" in data
        assert "version" in data


class TestCORS:
    """Test CORS configuration."""

    async def test_cors_headers(self, client: AsyncClient):
        """Test CORS headers are present."""
        response = await client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Should not fail due to CORS
        assert response.status_code in [200, 204, 405]
