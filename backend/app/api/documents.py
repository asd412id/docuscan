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
from app.utils.security import validate_path_within_directory
from app.utils.rate_limit import limiter


router = APIRouter()
settings = get_settings()

ALLOWED_MIME_TYPES = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/tiff",
    "image/bmp",
]


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
    # Validate file type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}",
        )

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Validate file size
    max_size = settings.max_upload_size_mb * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {settings.max_upload_size_mb}MB",
        )

    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1] or ".jpg"
    stored_filename = f"{uuid.uuid4()}{file_ext}"

    # Create user directory
    user_dir = os.path.join(settings.upload_dir, str(current_user.uuid))
    os.makedirs(user_dir, exist_ok=True)

    file_path = os.path.join(user_dir, stored_filename)

    # Save file
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Calculate expiration
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.file_retention_minutes
    )

    # Create document record
    document = Document(
        user_id=current_user.id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        file_path=file_path,
        file_size=file_size,
        mime_type=file.content_type,
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

    for file in files:
        # Validate file type
        if file.content_type not in ALLOWED_MIME_TYPES:
            continue  # Skip invalid files

        content = await file.read()
        file_size = len(content)

        max_size = settings.max_upload_size_mb * 1024 * 1024
        if file_size > max_size:
            continue  # Skip oversized files

        file_ext = os.path.splitext(file.filename)[1] or ".jpg"
        stored_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(user_dir, stored_filename)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.file_retention_minutes
        )

        document = Document(
            user_id=current_user.id,
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=file.content_type,
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
async def get_original_image(
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

    return FileResponse(
        document.file_path,
        media_type=document.mime_type,
        filename=document.original_filename,
    )


@router.get("/{document_uuid}/processed")
async def get_processed_image(
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

    return FileResponse(
        document.processed_path,
        media_type="image/jpeg",
        filename=f"scanned_{document.original_filename}",
    )


@router.get("/{document_uuid}/thumbnail")
async def get_thumbnail(
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

    return FileResponse(
        document.thumbnail_path,
        media_type="image/jpeg",
        filename=f"thumb_{document.original_filename}",
    )


@router.get("/{document_uuid}/preview")
async def get_preview_image(
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

    return FileResponse(
        preview_path,
        media_type="image/jpeg",
        filename=f"preview_{document.original_filename}",
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
    remaining_docs = await db.execute(
        select(Document).where(
            Document.user_id == current_user.id, Document.uuid != document_uuid
        )
    )
    is_last_document = remaining_docs.scalar_one_or_none() is None

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
    remaining_docs = await db.execute(
        select(Document).where(Document.user_id == current_user.id)
    )
    is_empty = remaining_docs.scalar_one_or_none() is None

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
