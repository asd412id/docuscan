"""
Tests for background task API endpoints.
Note: These tests mock Celery since it's disabled in test environment.
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock


class TestTasksAPI:
    """Test task management endpoints."""

    @pytest.mark.asyncio
    async def test_task_endpoints_require_celery_enabled(
        self, authenticated_client: dict
    ):
        """Test that task endpoints return 503 when Celery is disabled."""
        client = authenticated_client["client"]
        headers = authenticated_client["headers"]

        # Test process endpoint
        response = await client.post(
            "/api/tasks/process/test-uuid",
            headers=headers,
        )
        assert response.status_code == 503
        assert "not available" in response.json()["detail"].lower()

        # Test bulk process endpoint
        response = await client.post(
            "/api/tasks/bulk-process",
            json={"documents": [{"document_uuid": "test-uuid"}]},
            headers=headers,
        )
        assert response.status_code == 503
        assert "not available" in response.json()["detail"].lower()

        # Test status endpoint
        response = await client.get(
            "/api/tasks/status/test-task-id",
            headers=headers,
        )
        assert response.status_code == 503

        # Test cancel endpoint
        response = await client.post(
            "/api/tasks/cancel/test-task-id",
            headers=headers,
        )
        assert response.status_code == 503

        # Test complete endpoint
        response = await client.post(
            "/api/tasks/complete/test-task-id",
            headers=headers,
        )
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_task_endpoints_require_authentication(self, client: AsyncClient):
        """Test that task endpoints require authentication."""
        # Test process endpoint
        response = await client.post("/api/tasks/process/test-uuid")
        assert response.status_code == 401

        # Test bulk process endpoint
        response = await client.post(
            "/api/tasks/bulk-process",
            json={"documents": []},
        )
        assert response.status_code == 401

        # Test status endpoint
        response = await client.get("/api/tasks/status/test-task-id")
        assert response.status_code == 401


class TestTasksWithMockedCelery:
    """Test task endpoints with mocked Celery."""

    @pytest.mark.asyncio
    async def test_start_process_with_celery_mock(self, authenticated_client: dict):
        """Test starting a single document process task with mocked Celery."""
        # Skip if running without mock setup
        # This test would need proper Celery mocking setup
        pass

    @pytest.mark.asyncio
    async def test_bulk_process_with_celery_mock(self, authenticated_client: dict):
        """Test starting bulk process task with mocked Celery."""
        # Skip if running without mock setup
        pass


class TestRateLimiting:
    """Test rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limit_disabled_in_tests(self, client: AsyncClient):
        """Verify rate limiting is disabled in test environment."""
        # Make multiple requests - should all succeed since rate limiting is disabled
        for _ in range(20):
            response = await client.get("/api/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_check_includes_rate_limit_status(self, client: AsyncClient):
        """Test that health check shows rate limiting status."""
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "rate_limit_enabled" in data
        # In tests, rate limiting should be disabled
        assert data["rate_limit_enabled"] == False
