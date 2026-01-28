"""Tests for scanner service."""

import pytest
import numpy as np
from PIL import Image
import io


class TestScannerService:
    """Test document scanner service."""

    def test_scanner_import(self):
        """Test scanner service can be imported."""
        from app.services.scanner_service import DocumentScanner, scanner

        assert scanner is not None
        assert isinstance(scanner, DocumentScanner)

    def test_create_thumbnail(self):
        """Test thumbnail creation."""
        from app.services.scanner_service import scanner

        # Create a test image
        test_image = np.zeros((1000, 800, 3), dtype=np.uint8)
        test_image[:, :] = [255, 255, 255]  # White background

        thumbnail = scanner.create_thumbnail(test_image, max_size=300)

        assert thumbnail is not None
        assert max(thumbnail.shape[:2]) <= 300

    def test_order_points(self):
        """Test point ordering for perspective transform."""
        from app.services.scanner_service import scanner

        # Random points
        pts = np.array(
            [[100, 100], [400, 100], [400, 500], [100, 500]], dtype=np.float32
        )

        # Shuffle
        shuffled = pts[[2, 0, 3, 1]]

        ordered = scanner._order_points(shuffled)

        # Top-left should have smallest sum
        assert ordered[0].sum() < ordered[2].sum()

    def test_enhance_scan_grayscale(self):
        """Test grayscale enhancement."""
        from app.services.scanner_service import scanner

        # Create color image
        test_image = np.zeros((100, 100, 3), dtype=np.uint8)
        test_image[:50, :] = [255, 0, 0]  # Red top
        test_image[50:, :] = [0, 0, 255]  # Blue bottom

        result = scanner.enhance_scan(test_image, mode="grayscale", auto_enhance=False)

        assert result is not None
        assert result.shape == test_image.shape

    def test_enhance_scan_bw(self):
        """Test black & white enhancement."""
        from app.services.scanner_service import scanner

        test_image = np.zeros((100, 100, 3), dtype=np.uint8)
        test_image[:50, :] = [200, 200, 200]  # Light gray
        test_image[50:, :] = [50, 50, 50]  # Dark gray

        result = scanner.enhance_scan(test_image, mode="bw", auto_enhance=False)

        assert result is not None

    def test_rotate_image_90(self):
        """Test 90 degree rotation."""
        from app.services.scanner_service import scanner

        test_image = np.zeros((100, 200, 3), dtype=np.uint8)

        rotated = scanner.rotate_image(test_image, 90)

        assert rotated.shape[0] == 200  # Height becomes width
        assert rotated.shape[1] == 100  # Width becomes height

    def test_rotate_image_180(self):
        """Test 180 degree rotation."""
        from app.services.scanner_service import scanner

        test_image = np.zeros((100, 200, 3), dtype=np.uint8)

        rotated = scanner.rotate_image(test_image, 180)

        assert rotated.shape == test_image.shape

    def test_adjust_brightness_contrast(self):
        """Test brightness and contrast adjustment."""
        from app.services.scanner_service import scanner

        test_image = np.ones((100, 100, 3), dtype=np.uint8) * 128

        # Increase brightness
        bright = scanner._adjust_brightness_contrast(
            test_image, brightness=50, contrast=0
        )
        assert bright.mean() > test_image.mean()

        # Decrease brightness
        dark = scanner._adjust_brightness_contrast(
            test_image, brightness=-50, contrast=0
        )
        assert dark.mean() < test_image.mean()

    def test_perspective_transform(self):
        """Test perspective transformation."""
        from app.services.scanner_service import scanner

        # Create test image
        test_image = np.zeros((500, 400, 3), dtype=np.uint8)
        test_image[:, :] = [255, 255, 255]

        # Define corners (full image)
        corners = np.array([[0, 0], [399, 0], [399, 499], [0, 499]], dtype=np.float32)

        result = scanner.perspective_transform(test_image, corners)

        assert result is not None
        assert result.shape[0] > 0
        assert result.shape[1] > 0
