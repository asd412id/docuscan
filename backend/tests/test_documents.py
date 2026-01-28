"""Tests for document endpoints."""

import pytest
from httpx import AsyncClient
import io


class TestDocumentUpload:
    """Test document upload functionality."""

    async def test_upload_requires_auth(self, client: AsyncClient):
        """Test upload requires authentication."""
        # Create a simple test image
        files = {"file": ("test.jpg", b"fake image content", "image/jpeg")}
        response = await client.post("/api/documents/upload", files=files)
        assert response.status_code == 401

    async def test_upload_invalid_file_type(self, authenticated_client):
        """Test upload rejects invalid file types."""
        client = authenticated_client["client"]
        headers = authenticated_client["headers"]

        files = {"file": ("test.txt", b"text content", "text/plain")}
        response = await client.post(
            "/api/documents/upload", files=files, headers=headers
        )
        assert response.status_code in [400, 422]


class TestDocumentList:
    """Test document listing."""

    async def test_list_requires_auth(self, client: AsyncClient):
        """Test list requires authentication."""
        response = await client.get("/api/documents/")
        assert response.status_code == 401

    async def test_list_empty(self, authenticated_client):
        """Test list returns empty when no documents."""
        client = authenticated_client["client"]
        headers = authenticated_client["headers"]

        response = await client.get("/api/documents/", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "total" in data
