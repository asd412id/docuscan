"""
Security utilities for path validation, filename sanitization, and CSRF protection.
"""

import os
import re
import secrets
import unicodedata
from typing import Optional, Set, Tuple, Dict, List
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Allowed file extensions for image uploads (whitelist approach)
ALLOWED_IMAGE_EXTENSIONS: Set[str] = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tiff",
    ".tif",
    ".bmp",
    ".heic",
    ".heif",
}

# Dangerous file extensions that should never be allowed
DANGEROUS_EXTENSIONS: Set[str] = {
    ".exe",
    ".dll",
    ".bat",
    ".cmd",
    ".com",
    ".msi",
    ".scr",
    ".ps1",
    ".vbs",
    ".js",
    ".jse",
    ".wsf",
    ".wsh",
    ".php",
    ".phtml",
    ".asp",
    ".aspx",
    ".jsp",
    ".py",
    ".pl",
    ".rb",
    ".sh",
    ".bash",
    ".htaccess",
    ".htpasswd",
}

# Magic bytes (file signatures) for image validation
# Maps file type to list of valid magic byte signatures
IMAGE_MAGIC_BYTES: Dict[str, List[bytes]] = {
    "jpeg": [
        b"\xff\xd8\xff\xe0",  # JPEG JFIF
        b"\xff\xd8\xff\xe1",  # JPEG Exif
        b"\xff\xd8\xff\xe2",  # JPEG CIFF
        b"\xff\xd8\xff\xe3",  # JPEG Samsung
        b"\xff\xd8\xff\xe8",  # JPEG SPIFF
        b"\xff\xd8\xff\xdb",  # JPEG raw
        b"\xff\xd8\xff\xee",  # JPEG Adobe
    ],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "gif": [b"GIF87a", b"GIF89a"],
    "webp": [b"RIFF"],  # WebP starts with RIFF, need to check WEBP at offset 8
    "bmp": [b"BM"],
    "tiff": [b"II\x2a\x00", b"MM\x00\x2a"],  # Little-endian and big-endian TIFF
    "heic": [b"\x00\x00\x00"],  # HEIC starts with ftyp box, complex detection
}

# Extension to magic type mapping
EXTENSION_TO_MAGIC_TYPE: Dict[str, str] = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".gif": "gif",
    ".webp": "webp",
    ".bmp": "bmp",
    ".tiff": "tiff",
    ".tif": "tiff",
    ".heic": "heic",
    ".heif": "heic",
}


def validate_file_extension(
    filename: str, allowed_extensions: Set[str] = None
) -> Tuple[bool, str]:
    """
    Validate that a file extension is in the allowed whitelist.

    Args:
        filename: The filename to validate
        allowed_extensions: Set of allowed extensions (default: ALLOWED_IMAGE_EXTENSIONS)

    Returns:
        Tuple of (is_valid, sanitized_extension)
    """
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_IMAGE_EXTENSIONS

    if not filename:
        return False, ""

    # Get extension and normalize
    _, ext = os.path.splitext(filename)
    ext = ext.lower().strip()

    # Check for null bytes or other malicious content in extension
    if "\x00" in ext or ".." in ext or "/" in ext or "\\" in ext:
        logger.warning(f"Malicious extension detected: {repr(ext)}")
        return False, ""

    # Check against dangerous extensions
    if ext in DANGEROUS_EXTENSIONS:
        logger.warning(f"Dangerous extension blocked: {ext}")
        return False, ""

    # Check against whitelist
    if ext not in allowed_extensions:
        return False, ext

    return True, ext


def get_safe_file_extension(filename: str, default: str = ".jpg") -> str:
    """
    Get a safe file extension from filename, falling back to default if invalid.

    Args:
        filename: The filename to extract extension from
        default: Default extension if validation fails

    Returns:
        Safe file extension
    """
    is_valid, ext = validate_file_extension(filename)
    if is_valid and ext:
        return ext
    return default


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize a filename to remove potentially dangerous characters.

    - Removes path separators (/, \\)
    - Removes null bytes
    - Removes control characters
    - Normalizes unicode
    - Limits length

    Args:
        filename: The filename to sanitize
        max_length: Maximum allowed length for the filename

    Returns:
        Sanitized filename safe for use in archives and filesystem
    """
    if not filename:
        return "unnamed"

    # Normalize unicode characters
    filename = unicodedata.normalize("NFKD", filename)

    # Remove null bytes
    filename = filename.replace("\x00", "")

    # Remove path separators and other dangerous characters
    # This prevents path traversal attacks
    dangerous_chars = r'[<>:"/\\|?*\x00-\x1f]'
    filename = re.sub(dangerous_chars, "_", filename)

    # Remove leading/trailing dots and spaces (Windows restriction)
    filename = filename.strip(". ")

    # Collapse multiple underscores
    filename = re.sub(r"_+", "_", filename)

    # Ensure filename is not empty after sanitization
    if not filename:
        filename = "unnamed"

    # Truncate to max length while preserving extension
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        max_name_length = max_length - len(ext)
        if max_name_length > 0:
            filename = name[:max_name_length] + ext
        else:
            filename = filename[:max_length]

    return filename


def sanitize_filename_for_header(filename: str) -> str:
    """
    Sanitize a filename for use in HTTP Content-Disposition headers.

    This function ensures the filename is safe for use in HTTP headers,
    removing characters that could cause header injection or parsing issues.

    Args:
        filename: The filename to sanitize

    Returns:
        Sanitized filename safe for HTTP headers
    """
    if not filename:
        return "download"

    # First apply general sanitization
    safe_name = sanitize_filename(filename, max_length=200)

    # Additional sanitization for HTTP headers
    # Remove any remaining quotes, newlines, carriage returns
    safe_name = re.sub(r'[\r\n"\']', "", safe_name)

    # Ensure it's ASCII-safe for basic Content-Disposition
    # Non-ASCII characters are replaced with underscores
    # (for proper non-ASCII support, use RFC 5987 filename* parameter)
    try:
        safe_name.encode("ascii")
    except UnicodeEncodeError:
        # Replace non-ASCII with underscores
        safe_name = safe_name.encode("ascii", errors="replace").decode("ascii")
        safe_name = safe_name.replace("?", "_")

    if not safe_name:
        return "download"

    return safe_name


def validate_path_within_directory(path: str, base_directory: str) -> bool:
    """
    Validate that a path is within the expected base directory.
    Prevents path traversal attacks including symlink attacks.

    Args:
        path: The path to validate
        base_directory: The base directory that path should be within

    Returns:
        True if path is safely within base_directory, False otherwise
    """
    # Use realpath to resolve symlinks and get canonical path
    # This prevents symlink-based path traversal attacks
    try:
        abs_path = os.path.realpath(path)
        abs_base = os.path.realpath(base_directory)
    except (OSError, ValueError):
        # If path resolution fails, deny access
        return False

    # Ensure base directory ends with separator for proper prefix matching
    if not abs_base.endswith(os.sep):
        abs_base = abs_base + os.sep

    # Check if the path starts with the base directory
    return abs_path.startswith(abs_base) or abs_path == abs_base.rstrip(os.sep)


def get_safe_path(base_directory: str, *path_parts: str) -> Optional[str]:
    """
    Safely join path parts and validate the result is within base_directory.

    Args:
        base_directory: The base directory
        *path_parts: Path parts to join (will be sanitized)

    Returns:
        Safe absolute path if valid, None if path traversal detected
    """
    # Sanitize each path part
    safe_parts = []
    for part in path_parts:
        if part:
            # Remove any path separators from individual parts
            safe_part = part.replace("/", "_").replace("\\", "_")
            safe_part = safe_part.replace("..", "_")
            safe_parts.append(safe_part)

    if not safe_parts:
        return None

    # Join the paths
    full_path = os.path.join(base_directory, *safe_parts)

    # Validate the result is within base directory
    if validate_path_within_directory(full_path, base_directory):
        # Use realpath to get canonical path (resolves symlinks)
        try:
            return os.path.realpath(full_path)
        except (OSError, ValueError):
            return None

    return None


def validate_file_path_in_upload_dir(file_path: str, upload_dir: str) -> bool:
    """
    Validate that a file path from database is within the upload directory.
    Use this before serving files via FileResponse.

    Args:
        file_path: The file path to validate (from database)
        upload_dir: The configured upload directory

    Returns:
        True if file_path is safely within upload_dir
    """
    if not file_path:
        return False

    return validate_path_within_directory(file_path, upload_dir)


def validate_image_magic_bytes(
    file_content: bytes, claimed_extension: str
) -> Tuple[bool, str]:
    """
    Validate that file content matches the claimed file extension using magic bytes.

    This prevents attacks where malicious files are uploaded with image extensions.

    Args:
        file_content: The first bytes of the file (at least 16 bytes recommended)
        claimed_extension: The file extension claimed by the upload (e.g., ".jpg")

    Returns:
        Tuple of (is_valid, detected_type or error message)
    """
    if not file_content:
        return False, "Empty file content"

    if len(file_content) < 8:
        return False, "File too small for magic byte validation"

    # Normalize extension
    ext = claimed_extension.lower().strip()
    if not ext.startswith("."):
        ext = "." + ext

    # Get expected magic type for this extension
    expected_type = EXTENSION_TO_MAGIC_TYPE.get(ext)
    if not expected_type:
        # Unknown extension, can't validate
        return False, f"Unknown image extension: {ext}"

    # Check magic bytes for the expected type
    valid_signatures = IMAGE_MAGIC_BYTES.get(expected_type, [])

    for signature in valid_signatures:
        if file_content.startswith(signature):
            # Special case for WebP: need to verify "WEBP" at offset 8
            if expected_type == "webp":
                if len(file_content) >= 12 and file_content[8:12] == b"WEBP":
                    return True, expected_type
                continue
            # Special case for HEIC/HEIF: complex ftyp box detection
            if expected_type == "heic":
                # HEIC files have ftyp box, check for heic/heif/mif1 brand
                if len(file_content) >= 12:
                    # ftyp box: size(4) + 'ftyp'(4) + brand(4)
                    if file_content[4:8] == b"ftyp":
                        brand = file_content[8:12]
                        if brand in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
                            return True, expected_type
                continue
            return True, expected_type

    # No matching signature found
    # Try to detect what the file actually is
    detected_type = _detect_image_type(file_content)
    if detected_type:
        return False, f"File appears to be {detected_type}, not {expected_type}"
    return False, f"File does not match expected {expected_type} format"


def _detect_image_type(file_content: bytes) -> Optional[str]:
    """
    Attempt to detect the actual image type from magic bytes.

    Args:
        file_content: The first bytes of the file

    Returns:
        Detected image type or None if unknown
    """
    for img_type, signatures in IMAGE_MAGIC_BYTES.items():
        for signature in signatures:
            if file_content.startswith(signature):
                # Special handling for WebP
                if img_type == "webp":
                    if len(file_content) >= 12 and file_content[8:12] == b"WEBP":
                        return img_type
                    continue
                # Special handling for HEIC
                if img_type == "heic":
                    if len(file_content) >= 12 and file_content[4:8] == b"ftyp":
                        brand = file_content[8:12]
                        if brand in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
                            return img_type
                    continue
                return img_type
    return None


async def validate_uploaded_file_magic_bytes(
    file_content: bytes, filename: str
) -> Tuple[bool, str]:
    """
    Validate an uploaded file's magic bytes match its extension.

    This is an async-friendly wrapper for validate_image_magic_bytes.

    Args:
        file_content: First bytes of the uploaded file
        filename: Original filename with extension

    Returns:
        Tuple of (is_valid, error_message or "ok")
    """
    _, ext = os.path.splitext(filename)
    if not ext:
        return False, "File has no extension"

    is_valid, result = validate_image_magic_bytes(file_content, ext)
    if is_valid:
        return True, "ok"
    return False, result


# ============================================================================
# CSRF Protection
# ============================================================================

# CSRF token configuration
CSRF_TOKEN_LENGTH = 32  # 256 bits of entropy
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"

# Endpoints that don't require CSRF protection (safe methods and auth endpoints)
CSRF_EXEMPT_PATHS = {
    "/api/auth/token",  # Login (no existing session to protect)
    "/api/auth/register",  # Registration (no existing session)
    "/api/auth/refresh",  # Refresh uses httpOnly cookie for authentication
    "/api/health",  # Health check
}

# HTTP methods that don't modify state (safe methods)
CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def generate_csrf_token() -> str:
    """
    Generate a cryptographically secure CSRF token.

    Returns:
        Secure random token as URL-safe base64 string
    """
    return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)


def validate_csrf_token(
    cookie_token: Optional[str], header_token: Optional[str]
) -> bool:
    """
    Validate CSRF token using double-submit cookie pattern.

    The token in the cookie must match the token in the header.
    This works because:
    1. Attacker can't read cookies from another domain (same-origin policy)
    2. Attacker can't set custom headers on cross-origin requests

    Args:
        cookie_token: CSRF token from cookie
        header_token: CSRF token from request header

    Returns:
        True if tokens match and are valid, False otherwise
    """
    if not cookie_token or not header_token:
        return False

    # Constant-time comparison to prevent timing attacks
    return secrets.compare_digest(cookie_token, header_token)


def is_csrf_exempt(path: str, method: str) -> bool:
    """
    Check if a request is exempt from CSRF protection.

    Args:
        path: Request path
        method: HTTP method

    Returns:
        True if request doesn't need CSRF protection
    """
    # Safe methods don't need CSRF protection
    if method.upper() in CSRF_SAFE_METHODS:
        return True

    # Check if path is in exempt list
    if path in CSRF_EXEMPT_PATHS:
        return True

    # Also exempt paths that start with exempt prefixes
    for exempt_path in CSRF_EXEMPT_PATHS:
        if path.startswith(exempt_path):
            return True

    return False
