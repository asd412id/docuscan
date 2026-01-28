"""
Document Scanner Service using OpenCV.
Uses multiple detection methods including Hough Lines for better edge detection.
"""

import cv2
import numpy as np
from typing import List, Optional, Tuple
import math


def angle_cos(p0, p1, p2):
    """Calculate cosine of angle at p1 formed by p0-p1-p2."""
    d1, d2 = (p0 - p1).astype("float"), (p2 - p1).astype("float")
    denom = np.sqrt(np.dot(d1, d1) * np.dot(d2, d2))
    if denom < 1e-10:
        return 0
    return abs(np.dot(d1, d2) / denom)


def line_intersection(line1, line2):
    """Find intersection point of two lines defined by (rho, theta)."""
    rho1, theta1 = line1
    rho2, theta2 = line2

    cos1, sin1 = np.cos(theta1), np.sin(theta1)
    cos2, sin2 = np.cos(theta2), np.sin(theta2)

    denom = cos1 * sin2 - cos2 * sin1
    if abs(denom) < 1e-10:
        return None

    x = (sin2 * rho1 - sin1 * rho2) / denom
    y = (cos1 * rho2 - cos2 * rho1) / denom

    return (x, y)


class DocumentScanner:
    """
    Professional document scanner using OpenCV.
    Uses multiple detection approaches for robust document detection.
    """

    def __init__(self):
        self.min_area_ratio = 0.05
        self.max_area_ratio = 0.98

    def detect_document_edges(self, image: np.ndarray) -> Optional[np.ndarray]:
        """
        Detect document edges using multiple approaches.
        Returns array of 4 corner points [[x,y], ...] in order: TL, TR, BR, BL
        """
        original_height, original_width = image.shape[:2]

        # Resize for faster processing
        max_dim = 1000
        scale = min(max_dim / original_width, max_dim / original_height, 1.0)
        if scale < 1.0:
            resized = cv2.resize(
                image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
            )
        else:
            resized = image.copy()

        # Try multiple detection methods
        all_quads = []

        # Method 1: Contour-based detection
        contour_quads = self._find_contour_quads(resized)
        all_quads.extend(contour_quads)

        # Method 2: Hough Line based detection
        hough_quads = self._find_hough_quads(resized)
        all_quads.extend(hough_quads)

        # Method 3: Brightness-based detection for white documents
        bright_quads = self._find_bright_regions(resized)
        all_quads.extend(bright_quads)

        if not all_quads:
            return None

        # Select the best quadrilateral
        best = self._select_best_document(all_quads, resized)

        if best is not None:
            # Refine corners with sub-pixel accuracy
            refined = self._refine_corners(resized, best)

            # Scale back to original size
            ordered = self._order_points(refined)
            return (ordered / scale).astype(np.float32)

        return None

    def _find_hough_quads(self, img: np.ndarray) -> List[np.ndarray]:
        """
        Find document quadrilaterals using Hough Line Transform.
        This is particularly effective for documents with clear straight edges.
        """
        quads = []
        height, width = img.shape[:2]

        # Convert to grayscale and apply edge detection
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        # Use adaptive threshold for better edge detection
        edges = cv2.Canny(blur, 50, 150, apertureSize=3)

        # Dilate edges to close gaps
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)

        # Detect lines using Hough Transform
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)

        if lines is None or len(lines) < 4:
            return quads

        # Classify lines as horizontal or vertical
        horizontal_lines = []
        vertical_lines = []

        for line in lines:
            rho, theta = line[0]
            # Horizontal: theta close to 0 or pi
            # Vertical: theta close to pi/2
            angle_deg = np.degrees(theta)

            if angle_deg < 30 or angle_deg > 150:
                horizontal_lines.append((rho, theta))
            elif 60 < angle_deg < 120:
                vertical_lines.append((rho, theta))

        if len(horizontal_lines) < 2 or len(vertical_lines) < 2:
            return quads

        # Sort lines by rho to find top/bottom and left/right
        horizontal_lines.sort(key=lambda x: x[0])
        vertical_lines.sort(key=lambda x: x[0])

        # Try combinations of lines to form quadrilaterals
        # Take first and last of each category (hopefully document edges)
        h_candidates = [horizontal_lines[0], horizontal_lines[-1]]
        v_candidates = [vertical_lines[0], vertical_lines[-1]]

        # Also try some middle lines if available
        if len(horizontal_lines) > 4:
            h_candidates.extend([horizontal_lines[1], horizontal_lines[-2]])
        if len(vertical_lines) > 4:
            v_candidates.extend([vertical_lines[1], vertical_lines[-2]])

        # Find intersections to create quadrilaterals
        for h1 in h_candidates:
            for h2 in h_candidates:
                if h1 == h2:
                    continue
                for v1 in v_candidates:
                    for v2 in v_candidates:
                        if v1 == v2:
                            continue

                        # Get four corners
                        corners = []
                        for h in [h1, h2]:
                            for v in [v1, v2]:
                                pt = line_intersection(h, v)
                                if pt is not None:
                                    corners.append(pt)

                        if len(corners) != 4:
                            continue

                        # Check if corners are within image bounds
                        corners = np.array(corners)
                        if (
                            np.any(corners < -50)
                            or np.any(corners[:, 0] > width + 50)
                            or np.any(corners[:, 1] > height + 50)
                        ):
                            continue

                        # Clip to image bounds
                        corners[:, 0] = np.clip(corners[:, 0], 0, width - 1)
                        corners[:, 1] = np.clip(corners[:, 1], 0, height - 1)

                        # Check area
                        area = cv2.contourArea(corners.astype(np.float32))
                        img_area = width * height

                        if (
                            self.min_area_ratio * img_area
                            < area
                            < self.max_area_ratio * img_area
                        ):
                            # Check if convex
                            ordered = self._order_points(corners)
                            if cv2.isContourConvex(ordered.astype(np.int32)):
                                quads.append(ordered)

        return quads

    def _find_contour_quads(self, img: np.ndarray) -> List[np.ndarray]:
        """Find quadrilaterals using contour detection."""
        squares = []
        img_area = img.shape[0] * img.shape[1]

        # Preprocess
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        # Try multiple edge detection methods
        edge_images = []

        # Canny with different thresholds
        edge_images.append(cv2.Canny(blur, 30, 100))
        edge_images.append(cv2.Canny(blur, 50, 150))
        edge_images.append(cv2.Canny(blur, 75, 200))

        # Adaptive threshold
        adaptive = cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        edge_images.append(adaptive)

        for edges in edge_images:
            # Dilate to close gaps
            kernel = np.ones((3, 3), np.uint8)
            dilated = cv2.dilate(edges, kernel, iterations=1)

            # Find contours
            contours, _ = cv2.findContours(
                dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            for cnt in contours:
                # Approximate contour
                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

                if len(approx) == 4 and cv2.isContourConvex(approx):
                    area = cv2.contourArea(approx)
                    if (
                        self.min_area_ratio * img_area
                        < area
                        < self.max_area_ratio * img_area
                    ):
                        approx = approx.reshape(-1, 2).astype(np.float32)

                        # Check angles
                        max_cos = np.max(
                            [
                                angle_cos(
                                    approx[i], approx[(i + 1) % 4], approx[(i + 2) % 4]
                                )
                                for i in range(4)
                            ]
                        )
                        if max_cos < 0.3:
                            squares.append(approx)

        return squares

    def _find_bright_regions(self, img: np.ndarray) -> List[np.ndarray]:
        """Find bright regions (white documents on colored backgrounds)."""
        squares = []
        img_area = img.shape[0] * img.shape[1]

        # Convert to LAB color space for better brightness detection
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]

        # Also use HSV for saturation
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        s_channel = hsv[:, :, 1]

        # Otsu threshold on L channel
        _, bright_mask = cv2.threshold(
            l_channel, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # Low saturation mask
        _, low_sat_mask = cv2.threshold(s_channel, 60, 255, cv2.THRESH_BINARY_INV)

        # Combine: bright AND low saturation = likely paper
        paper_mask = cv2.bitwise_and(bright_mask, low_sat_mask)

        # Clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        paper_mask = cv2.morphologyEx(paper_mask, cv2.MORPH_CLOSE, kernel)
        paper_mask = cv2.morphologyEx(paper_mask, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(
            paper_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for cnt in contours:
            peri = cv2.arcLength(cnt, True)
            if peri < 100:
                continue

            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

            if len(approx) == 4 and cv2.isContourConvex(approx):
                area = cv2.contourArea(approx)
                if (
                    self.min_area_ratio * img_area
                    < area
                    < self.max_area_ratio * img_area
                ):
                    approx = approx.reshape(-1, 2).astype(np.float32)
                    max_cos = np.max(
                        [
                            angle_cos(
                                approx[i], approx[(i + 1) % 4], approx[(i + 2) % 4]
                            )
                            for i in range(4)
                        ]
                    )
                    if max_cos < 0.4:
                        squares.append(approx)

        return squares

    def _refine_corners(self, img: np.ndarray, quad: np.ndarray) -> np.ndarray:
        """Refine corner positions using sub-pixel accuracy."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Prepare corners for refinement
        corners = quad.reshape(-1, 1, 2).astype(np.float32)

        # Define criteria for corner refinement
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.001)

        try:
            # Refine corners with sub-pixel accuracy
            refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            return refined.reshape(-1, 2)
        except Exception:
            return quad

    def _select_best_document(
        self, quads: List[np.ndarray], image: np.ndarray
    ) -> Optional[np.ndarray]:
        """Select the best document candidate based on scoring."""
        if not quads:
            return None

        img_area = image.shape[0] * image.shape[1]
        height, width = image.shape[:2]

        scored = []
        for quad in quads:
            score = self._score_document(quad, img_area, width, height, image)
            scored.append((score, quad))

        scored.sort(key=lambda x: x[0], reverse=True)

        if scored:
            return scored[0][1]

        return None

    def _score_document(
        self,
        quad: np.ndarray,
        img_area: float,
        img_width: int,
        img_height: int,
        image: np.ndarray,
    ) -> float:
        """Score a quadrilateral based on document-like properties."""
        score = 0.0

        # 1. Area score
        area = cv2.contourArea(quad.astype(np.float32))
        area_ratio = area / img_area

        if 0.30 <= area_ratio <= 0.85:
            score += 50 + (area_ratio * 30)
        elif area_ratio > 0.85:
            score += 40
        else:
            score += area_ratio * 100

        # 2. Rectangularity score
        ordered = self._order_points(quad)
        max_cos = np.max(
            [
                angle_cos(ordered[i], ordered[(i + 1) % 4], ordered[(i + 2) % 4])
                for i in range(4)
            ]
        )
        score += (1 - max_cos) * 30

        # 3. Aspect ratio score
        w = (
            np.linalg.norm(ordered[0] - ordered[1])
            + np.linalg.norm(ordered[3] - ordered[2])
        ) / 2
        h = (
            np.linalg.norm(ordered[0] - ordered[3])
            + np.linalg.norm(ordered[1] - ordered[2])
        ) / 2

        if w > 0 and h > 0:
            aspect = max(w, h) / min(w, h)
            if 1.0 <= aspect <= 2.0:
                score += 20
            elif aspect <= 2.5:
                score += 10

        # 4. Content brightness analysis - MOST IMPORTANT
        try:
            mask = np.zeros(image.shape[:2], dtype=np.uint8)
            cv2.fillPoly(mask, [quad.astype(np.int32)], 255)
            exterior_mask = cv2.bitwise_not(mask)

            # Brightness analysis
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            interior_brightness = cv2.mean(gray, mask)[0]
            exterior_brightness = cv2.mean(gray, exterior_mask)[0]

            brightness_diff = interior_brightness - exterior_brightness
            if brightness_diff > 0:
                score += min(100, brightness_diff * 2.5)
            else:
                score += max(-80, brightness_diff * 2.0)

            # Saturation analysis
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            interior_sat = cv2.mean(hsv[:, :, 1], mask)[0]
            exterior_sat = cv2.mean(hsv[:, :, 1], exterior_mask)[0]

            sat_diff = exterior_sat - interior_sat
            if sat_diff > 0:
                score += min(60, sat_diff * 1.2)

        except Exception:
            pass

        # 5. Edge distance - small penalty for corners too close to edge
        margin = 5
        edge_penalty = 0
        for point in quad:
            x, y = point
            if x <= margin or x >= img_width - margin:
                edge_penalty += 10
            if y <= margin or y >= img_height - margin:
                edge_penalty += 10

        score -= edge_penalty

        return score

    def _order_points(self, pts: np.ndarray) -> np.ndarray:
        """Order points: top-left, top-right, bottom-right, bottom-left."""
        rect = np.zeros((4, 2), dtype=np.float32)
        pts = pts.astype(np.float32)

        s = pts.sum(axis=1)
        diff = np.diff(pts, axis=1).flatten()

        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]

        return rect

    def perspective_transform(
        self,
        image: np.ndarray,
        corners: np.ndarray,
        target_width: Optional[int] = None,
        target_height: Optional[int] = None,
    ) -> np.ndarray:
        """Apply perspective transformation to extract and straighten the document."""
        ordered = self._order_points(corners)
        (tl, tr, br, bl) = ordered

        width_a = np.linalg.norm(br - bl)
        width_b = np.linalg.norm(tr - tl)
        max_width = int(max(width_a, width_b))

        height_a = np.linalg.norm(tr - br)
        height_b = np.linalg.norm(tl - bl)
        max_height = int(max(height_a, height_b))

        if target_width:
            max_width = target_width
        if target_height:
            max_height = target_height

        dst = np.array(
            [
                [0, 0],
                [max_width - 1, 0],
                [max_width - 1, max_height - 1],
                [0, max_height - 1],
            ],
            dtype=np.float32,
        )

        matrix = cv2.getPerspectiveTransform(ordered, dst)
        warped = cv2.warpPerspective(image, matrix, (max_width, max_height))

        return warped

    def enhance_scan(
        self,
        image: np.ndarray,
        mode: str = "color",
        brightness: float = 0,
        contrast: float = 0,
        auto_enhance: bool = True,
    ) -> np.ndarray:
        """Enhance the scanned document image."""
        result = image.copy()

        # For B&W mode, skip auto_enhance as it can cause issues
        if auto_enhance and mode != "bw":
            result = self._auto_enhance(result)

        if brightness != 0 or contrast != 0:
            result = self._adjust_brightness_contrast(result, brightness, contrast)

        if mode == "grayscale":
            if len(result.shape) == 3:
                result = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
                result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)
        elif mode == "bw":
            # Convert to grayscale
            if len(result.shape) == 3:
                gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
            else:
                gray = result.copy()

            # Use illumination normalization + clean threshold for document scanning
            # This avoids the "cartoon effect" from aggressive adaptive thresholding
            result = self._clean_document_binarization(gray)

            result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)

        return result

    def _clean_document_binarization(self, gray: np.ndarray) -> np.ndarray:
        """
        Clean document B&W processing - high contrast grayscale.

        Instead of forcing binary (0/255), we stretch the histogram
        to make whites whiter and blacks blacker while preserving gradients.
        """
        # Step 1: Light denoise
        denoised = cv2.GaussianBlur(gray, (3, 3), 0)

        # Step 2: Local normalization to handle uneven lighting
        # Use large kernel to estimate local background
        blur_size = 81  # larger = smoother normalization
        local_mean = cv2.GaussianBlur(denoised, (blur_size, blur_size), 0)

        # Normalize: pixel / local_mean * target_brightness
        # Higher target = brighter overall
        normalized = np.clip(
            denoised.astype(np.float32) / (local_mean.astype(np.float32) + 1) * 220,
            0,
            255,
        )

        # Step 3: Stretch histogram with tight percentiles
        p_low = np.percentile(normalized, 3)  # black point (text)
        p_high = np.percentile(
            normalized, 85
        )  # white point (paper) - lower = more aggressive whitening

        if p_high > p_low:
            stretched = np.clip((normalized - p_low) * 255.0 / (p_high - p_low), 0, 255)
        else:
            stretched = normalized

        # Step 4: Gamma correction - push background to white
        gamma = 0.55  # lower = brighter background
        stretched = 255.0 * np.power(stretched / 255.0, gamma)

        # Step 5: Final contrast boost
        result = np.clip(stretched * 1.4 - 50, 0, 255).astype(np.uint8)

        return result

    def _sauvola_threshold(
        self, gray: np.ndarray, window_size: int = 25, k: float = 0.2, r: float = 128
    ) -> np.ndarray:
        """
        Sauvola binarization - kept for reference/alternative use.

        T(x,y) = mean(x,y) * (1 + k * (std(x,y) / r - 1))

        Args:
            gray: Grayscale input image
            window_size: Size of the local window (must be odd)
            k: Sensitivity parameter (0.2-0.5, lower = less aggressive)
            r: Dynamic range of standard deviation (typically 128)
        """
        # Ensure window size is odd
        if window_size % 2 == 0:
            window_size += 1

        # Convert to float for calculations
        img = gray.astype(np.float64)

        # Calculate local mean using box filter
        mean = cv2.boxFilter(img, cv2.CV_64F, (window_size, window_size))

        # Calculate local standard deviation
        # std = sqrt(E[X^2] - E[X]^2)
        mean_sq = cv2.boxFilter(img**2, cv2.CV_64F, (window_size, window_size))
        std = np.sqrt(np.maximum(mean_sq - mean**2, 0))

        # Sauvola threshold formula
        threshold = mean * (1.0 + k * (std / r - 1.0))

        # Apply threshold
        binary = np.zeros_like(gray)
        binary[img > threshold] = 255

        return binary.astype(np.uint8)

    def _auto_enhance(self, image: np.ndarray) -> np.ndarray:
        """Apply automatic image enhancement for document scanning."""
        result = cv2.fastNlMeansDenoisingColored(image, None, 3, 3, 7, 21)

        lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
        l = clahe.apply(l)

        lab = cv2.merge([l, a, b])
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        gaussian = cv2.GaussianBlur(result, (0, 0), 2.0)
        result = cv2.addWeighted(result, 1.3, gaussian, -0.3, 0)

        return result

    def _adjust_brightness_contrast(
        self, image: np.ndarray, brightness: float, contrast: float
    ) -> np.ndarray:
        """Adjust brightness and contrast."""
        img_float = image.astype(np.float32)
        alpha = 1 + contrast / 100.0
        beta = brightness * 2.55

        result = cv2.convertScaleAbs(img_float, alpha=alpha, beta=beta)
        return result

    def rotate_image(self, image: np.ndarray, angle: int) -> np.ndarray:
        """Rotate image by specified angle (in degrees)."""
        if angle == 0:
            return image

        if angle == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            return cv2.rotate(image, cv2.ROTATE_180)
        elif angle == 270:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            height, width = image.shape[:2]
            center = (width / 2, height / 2)
            matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)

            cos = np.abs(matrix[0, 0])
            sin = np.abs(matrix[0, 1])
            new_width = int((height * sin) + (width * cos))
            new_height = int((height * cos) + (width * sin))

            matrix[0, 2] += (new_width / 2) - center[0]
            matrix[1, 2] += (new_height / 2) - center[1]

            return cv2.warpAffine(
                image, matrix, (new_width, new_height), borderValue=(255, 255, 255)
            )

    def deskew(self, image: np.ndarray) -> np.ndarray:
        """Automatically detect and correct skew in document image."""
        gray = (
            cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        )

        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, 100, minLineLength=100, maxLineGap=10
        )

        if lines is None:
            return image

        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            if abs(angle) < 45:
                angles.append(angle)

        if not angles:
            return image

        median_angle = np.median(angles)

        if 0.5 < abs(median_angle) < 10:
            return self.rotate_image(image, int(-median_angle))

        return image

    def create_thumbnail(self, image: np.ndarray, max_size: int = 300) -> np.ndarray:
        """Create a thumbnail of the image."""
        height, width = image.shape[:2]
        scale = min(max_size / width, max_size / height)
        new_width = int(width * scale)
        new_height = int(height * scale)

        return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)


# Singleton instance
scanner = DocumentScanner()
