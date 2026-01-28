from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from typing import Annotated, List
from datetime import datetime, timezone, timedelta
import os
import uuid
import shutil
import aiofiles
import logging

from app.database import get_db
from app.config import get_settings
from app.schemas.schemas import (
    DocumentResponse,
    DocumentListResponse,
    MessageResponse,
    BatchDeleteRequest,
)
from app.models.models import User, Document
from app.api.auth import get_current_user
from app.utils.security import (
    validate_path_within_directory,
    validate_file_extension,
    get_safe_file_extension,
    sanitize_filename,
    sanitize_filename_for_header,
    validate_uploaded_file_magic_bytes,
)
from app.utils.rate_limit import limiter


router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/tiff",
    "image/bmp",
    "image/heic",
    "image/heif",
]

# Some mobile browsers send these content types for camera photos
CAMERA_MIME_ALIASES = {
    "image/jpg": "image/jpeg",
    "application/octet-stream": None,  # Will be detected from extension
}


def normalize_mime_type(content_type: str | None, filename: str) -> str:
    """Normalize MIME type, handling camera photo edge cases."""
    if content_type in CAMERA_MIME_ALIASES:
        if CAMERA_MIME_ALIASES[content_type] is not None:
            return CAMERA_MIME_ALIASES[content_type]
        # Detect from extension
        ext = os.path.splitext(filename)[1].lower()
        ext_to_mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
            ".bmp": "image/bmp",
            ".heic": "image/heic",
            ".heif": "image/heif",
        }
        return ext_to_mime.get(ext, "application/octet-stream")

    if not content_type:
        return "application/octet-stream"

    return content_type


@router.post(
    "/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit(settings.rate_limit_upload)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document image for processing."""
    # Normalize and validate file type (handle camera photo edge cases)
    mime_type = normalize_mime_type(file.content_type, file.filename or "image.jpg")

    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}",
        )

    # Generate unique filename with validated extension
    file_ext = get_safe_file_extension(file.filename or "image.jpg", default=".jpg")
    stored_filename = f"{uuid.uuid4()}{file_ext}"

    # Create user directory
    user_dir = os.path.join(settings.upload_dir, str(current_user.uuid))
    os.makedirs(user_dir, exist_ok=True)

    file_path = os.path.join(user_dir, stored_filename)
    max_size = settings.max_upload_size_mb * 1024 * 1024

    # Stream file to disk in chunks to avoid loading entire file into memory
    file_size = 0
    try:
        async with aiofiles.open(file_path, "wb") as f:
            while True:
                chunk = await file.read(64 * 1024)  # 64KB chunks
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > max_size:
                    # Clean up partial file and raise error
                    await f.close()
                    os.remove(file_path)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"File too large. Maximum size: {settings.max_upload_size_mb}MB",
                    )
                await f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        # Clean up on any error
        if os.path.exists(file_path):
            os.remove(file_path)
        logger.error(f"Error writing file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file",
        )

    # If client sent a generic/empty content-type, infer from extension after reading
    if mime_type == "application/octet-stream":
        mime_type = normalize_mime_type(None, file.filename or "image.jpg")

    if mime_type not in ALLOWED_MIME_TYPES:
        os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}",
        )

    # Validate magic bytes match claimed file extension
    try:
        async with aiofiles.open(file_path, "rb") as f:
            header_bytes = await f.read(32)  # Read first 32 bytes for magic validation
        is_valid_magic, magic_error = await validate_uploaded_file_magic_bytes(
            header_bytes, file.filename or "image.jpg"
        )
        if not is_valid_magic:
            os.remove(file_path)
            logger.warning(
                f"Magic bytes validation failed for {file.filename}: {magic_error}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File content does not match claimed type: {magic_error}",
            )
    except HTTPException:
        raise
    except Exception as e:
        # If magic validation fails unexpectedly, log but allow (fallback to MIME check)
        logger.warning(f"Magic bytes validation error: {e}")

    # Calculate expiration
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.file_retention_minutes
    )

    # Create document record
    document = Document(
        user_id=current_user.id,
        original_filename=file.filename or "camera_photo.jpg",
        stored_filename=stored_filename,
        file_path=file_path,
        file_size=file_size,
        mime_type=mime_type,
        status="pending",
        expires_at=expires_at,
    )

    db.add(document)
    await db.flush()
    await db.refresh(document)

    return DocumentResponse(
        id=document.id,
        uuid=document.uuid,
        original_filename=document.original_filename,
        stored_filename=document.stored_filename,
        file_size=document.file_size,
        mime_type=document.mime_type,
        status=document.status,
        created_at=document.created_at,
    )


@router.post(
    "/upload-batch",
    response_model=List[DocumentResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(settings.rate_limit_upload)
async def upload_documents_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload multiple document images for batch processing."""
    if len(files) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum 20 files per batch"
        )

    documents = []
    user_dir = os.path.join(settings.upload_dir, str(current_user.uuid))
    os.makedirs(user_dir, exist_ok=True)
    max_size = settings.max_upload_size_mb * 1024 * 1024

    for file in files:
        # Normalize and validate file type (handle camera photo edge cases)
        mime_type = normalize_mime_type(file.content_type, file.filename or "image.jpg")

        if mime_type not in ALLOWED_MIME_TYPES:
            continue  # Skip invalid files

        if mime_type == "application/octet-stream":
            mime_type = normalize_mime_type(None, file.filename or "image.jpg")

        if mime_type not in ALLOWED_MIME_TYPES:
            continue

        # Validate file extension (security whitelist)
        is_valid_ext, _ = validate_file_extension(file.filename or "image.jpg")
        if not is_valid_ext:
            logger.warning(f"Invalid file extension blocked: {file.filename}")
            continue

        file_ext = get_safe_file_extension(file.filename or "image.jpg", default=".jpg")
        stored_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(user_dir, stored_filename)

        # Stream file to disk in chunks
        file_size = 0
        try:
            async with aiofiles.open(file_path, "wb") as f:
                while True:
                    chunk = await file.read(64 * 1024)  # 64KB chunks
                    if not chunk:
                        break
                    file_size += len(chunk)
                    if file_size > max_size:
                        await f.close()
                        os.remove(file_path)
                        break  # Skip oversized file
                    await f.write(chunk)

            if file_size > max_size:
                continue  # Skip this file, already cleaned up

            # Validate magic bytes match claimed file extension
            async with aiofiles.open(file_path, "rb") as f:
                header_bytes = await f.read(32)
            is_valid_magic, magic_error = await validate_uploaded_file_magic_bytes(
                header_bytes, file.filename or "image.jpg"
            )
            if not is_valid_magic:
                os.remove(file_path)
                logger.warning(
                    f"Magic bytes validation failed for {file.filename}: {magic_error}"
                )
                continue  # Skip invalid file
        except Exception as e:
            # Clean up on error and skip this file
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            logger.error(f"Error writing file {file.filename}: {e}")
            continue

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.file_retention_minutes
        )

        document = Document(
            user_id=current_user.id,
            original_filename=file.filename or "camera_photo.jpg",
            stored_filename=stored_filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            status="pending",
            expires_at=expires_at,
        )

        db.add(document)
        documents.append(document)

    await db.flush()

    for doc in documents:
        await db.refresh(doc)

    return [
        DocumentResponse(
            id=doc.id,
            uuid=doc.uuid,
            original_filename=doc.original_filename,
            stored_filename=doc.stored_filename,
            file_size=doc.file_size,
            mime_type=doc.mime_type,
            status=doc.status,
            created_at=doc.created_at,
        )
        for doc in documents
    ]


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's documents."""
    offset = (page - 1) * page_size

    # Get total count efficiently using SQL COUNT
    count_result = await db.execute(
        select(func.count(Document.id)).where(Document.user_id == current_user.id)
    )
    total = count_result.scalar() or 0

    # Get paginated documents
    result = await db.execute(
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    documents = result.scalars().all()

    return DocumentListResponse(
        documents=[
            DocumentResponse(
                id=doc.id,
                uuid=doc.uuid,
                original_filename=doc.original_filename,
                stored_filename=doc.stored_filename,
                file_size=doc.file_size,
                mime_type=doc.mime_type,
                status=doc.status,
                created_at=doc.created_at,
                thumbnail_url=f"/api/documents/{doc.uuid}/thumbnail"
                if doc.thumbnail_path
                else None,
                processed_url=f"/api/documents/{doc.uuid}/processed"
                if doc.processed_path
                else None,
            )
            for doc in documents
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_uuid}", response_model=DocumentResponse)
async def get_document(
    document_uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get document details."""
    result = await db.execute(
        select(Document).where(
            Document.uuid == document_uuid, Document.user_id == current_user.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    return DocumentResponse(
        id=document.id,
        uuid=document.uuid,
        original_filename=document.original_filename,
        stored_filename=document.stored_filename,
        file_size=document.file_size,
        mime_type=document.mime_type,
        status=document.status,
        created_at=document.created_at,
        thumbnail_url=f"/api/documents/{document.uuid}/thumbnail"
        if document.thumbnail_path
        else None,
        processed_url=f"/api/documents/{document.uuid}/processed"
        if document.processed_path
        else None,
    )


@router.get("/{document_uuid}/original")
@limiter.limit(settings.rate_limit_download)
async def get_original_image(
    request: Request,
    document_uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get original uploaded image."""
    result = await db.execute(
        select(Document).where(
            Document.uuid == document_uuid, Document.user_id == current_user.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    if not os.path.exists(document.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    # Validate file path is within upload directory (prevent serving arbitrary files)
    if not validate_path_within_directory(document.file_path, settings.upload_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Sanitize filename for Content-Disposition header
    safe_filename = sanitize_filename_for_header(document.original_filename)

    return FileResponse(
        document.file_path,
        media_type=document.mime_type,
        filename=safe_filename,
    )


@router.get("/{document_uuid}/processed")
@limiter.limit(settings.rate_limit_download)
async def get_processed_image(
    request: Request,
    document_uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get processed/scanned image."""
    result = await db.execute(
        select(Document).where(
            Document.uuid == document_uuid, Document.user_id == current_user.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    if not document.processed_path or not os.path.exists(document.processed_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Processed image not found"
        )

    # Validate file path is within upload directory
    if not validate_path_within_directory(document.processed_path, settings.upload_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Sanitize filename for Content-Disposition header
    safe_filename = sanitize_filename_for_header(
        f"scanned_{document.original_filename}"
    )

    return FileResponse(
        document.processed_path,
        media_type="image/jpeg",
        filename=safe_filename,
    )


@router.get("/{document_uuid}/thumbnail")
@limiter.limit(settings.rate_limit_download)
async def get_thumbnail(
    request: Request,
    document_uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get document thumbnail."""
    result = await db.execute(
        select(Document).where(
            Document.uuid == document_uuid, Document.user_id == current_user.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    if not document.thumbnail_path or not os.path.exists(document.thumbnail_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not found"
        )

    # Validate file path is within upload directory
    if not validate_path_within_directory(document.thumbnail_path, settings.upload_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Sanitize filename for Content-Disposition header
    safe_filename = sanitize_filename_for_header(f"thumb_{document.original_filename}")

    return FileResponse(
        document.thumbnail_path,
        media_type="image/jpeg",
        filename=safe_filename,
    )


@router.get("/{document_uuid}/preview")
@limiter.limit(settings.rate_limit_download)
async def get_preview_image(
    request: Request,
    document_uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get preview image with detected edges drawn on it."""
    result = await db.execute(
        select(Document).where(
            Document.uuid == document_uuid, Document.user_id == current_user.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    # Preview file is created during edge detection
    preview_path = os.path.join(
        os.path.dirname(document.file_path), f"preview_{document.stored_filename}"
    )

    if not os.path.exists(preview_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Preview not found"
        )

    # Validate file path is within upload directory
    if not validate_path_within_directory(preview_path, settings.upload_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Sanitize filename for Content-Disposition header
    safe_filename = sanitize_filename_for_header(
        f"preview_{document.original_filename}"
    )

    return FileResponse(
        preview_path,
        media_type="image/jpeg",
        filename=safe_filename,
    )


@router.delete("/{document_uuid}", response_model=MessageResponse)
async def delete_document(
    document_uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document."""
    result = await db.execute(
        select(Document).where(
            Document.uuid == document_uuid, Document.user_id == current_user.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    # Delete files including preview file
    user_dir = os.path.join(settings.upload_dir, str(current_user.uuid))
    exports_dir = os.path.join(user_dir, "exports")

    # Build list of files to delete
    files_to_delete = [
        document.file_path,
        document.processed_path,
        document.thumbnail_path,
    ]

    # Add preview file (created during edge detection)
    if document.file_path:
        preview_path = os.path.join(
            os.path.dirname(document.file_path), f"preview_{document.stored_filename}"
        )
        files_to_delete.append(preview_path)

    for path in files_to_delete:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass  # File may already be deleted

    # Check if this is the last document for this user
    remaining_count_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.user_id == current_user.id, Document.uuid != document_uuid
        )
    )
    remaining_count = remaining_count_result.scalar() or 0
    is_last_document = remaining_count == 0

    # If last document, clean up exports folder too
    if is_last_document and os.path.exists(exports_dir):
        try:
            shutil.rmtree(exports_dir)
        except OSError:
            pass

    # Try to remove user directory if empty
    try:
        if os.path.exists(user_dir) and not os.listdir(user_dir):
            os.rmdir(user_dir)
    except OSError:
        pass  # Directory not empty or other error

    # Delete record
    await db.delete(document)

    return MessageResponse(message="Document deleted successfully")


@router.delete("/exports/clear", response_model=MessageResponse)
async def clear_exports(
    current_user: User = Depends(get_current_user),
):
    """Clear all exported files for the current user."""
    user_dir = os.path.join(settings.upload_dir, str(current_user.uuid))
    exports_dir = os.path.join(user_dir, "exports")

    deleted_count = 0
    if os.path.exists(exports_dir):
        try:
            # Count files before deletion
            for f in os.listdir(exports_dir):
                file_path = os.path.join(exports_dir, f)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted_count += 1
        except OSError:
            pass

    return MessageResponse(message=f"Cleared {deleted_count} export files")


@router.post("/batch-delete", response_model=MessageResponse)
async def batch_delete_documents(
    request: BatchDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple documents at once."""
    if len(request.document_uuids) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 100 documents per batch delete",
        )

    # Get all documents to delete
    result = await db.execute(
        select(Document).where(
            Document.uuid.in_(request.document_uuids),
            Document.user_id == current_user.id,
        )
    )
    documents = list(result.scalars().all())

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No documents found"
        )

    user_dir = os.path.join(settings.upload_dir, str(current_user.uuid))
    deleted_count = 0

    for document in documents:
        # Build list of files to delete
        files_to_delete = [
            document.file_path,
            document.processed_path,
            document.thumbnail_path,
        ]

        # Add preview file
        if document.file_path:
            preview_path = os.path.join(
                os.path.dirname(document.file_path),
                f"preview_{document.stored_filename}",
            )
            files_to_delete.append(preview_path)

        for path in files_to_delete:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

        await db.delete(document)
        deleted_count += 1

    # Check if any documents remain
    remaining_count_result = await db.execute(
        select(func.count(Document.id)).where(Document.user_id == current_user.id)
    )
    remaining_count = remaining_count_result.scalar() or 0
    is_empty = remaining_count == 0

    # Clean up exports and user directory if empty
    if is_empty:
        exports_dir = os.path.join(user_dir, "exports")
        if os.path.exists(exports_dir):
            try:
                shutil.rmtree(exports_dir)
            except OSError:
                pass
        try:
            if os.path.exists(user_dir) and not os.listdir(user_dir):
                os.rmdir(user_dir)
        except OSError:
            pass

    return MessageResponse(message=f"Deleted {deleted_count} documents")
