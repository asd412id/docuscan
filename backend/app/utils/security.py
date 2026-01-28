"""
Security utilities for path validation and filename sanitization.
"""

import os
import re
import unicodedata
from typing import Optional


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


def validate_path_within_directory(path: str, base_directory: str) -> bool:
    """
    Validate that a path is within the expected base directory.
    Prevents path traversal attacks.

    Args:
        path: The path to validate
        base_directory: The base directory that path should be within

    Returns:
        True if path is safely within base_directory, False otherwise
    """
    # Resolve both paths to absolute, normalized paths
    abs_path = os.path.abspath(os.path.normpath(path))
    abs_base = os.path.abspath(os.path.normpath(base_directory))

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
        return os.path.abspath(os.path.normpath(full_path))

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
