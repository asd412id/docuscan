from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime, timezone, timedelta
import os
import uuid
import cv2
import numpy as np
import zipfile
import shutil

from app.database import get_db
from app.config import get_settings
from app.schemas.schemas import (
    DetectResponse,
    ProcessRequest,
    ProcessResponse,
    OCRResponse,
    ExportRequest,
    ExportResponse,
    CornerPoints,
    BulkProcessRequest,
)
from app.models.models import User, Document
from app.api.auth import get_current_user
from app.services.scanner_service import scanner
from app.services.ocr_service import ocr_service
from app.services.pdf_service import pdf_service
from app.utils.security import (
    sanitize_filename,
    get_safe_path,
    validate_path_within_directory,
)
from app.utils.rate_limit import limiter


router = APIRouter()
settings = get_settings()


@router.post("/detect/{document_uuid}", response_model=DetectResponse)
@limiter.limit(settings.rate_limit_process)
async def detect_document_edges(
    request: Request,
    document_uuid: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Detect document edges in the uploaded image.
    Returns corner points for perspective transformation.
    """
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

    # Load image
    image = cv2.imread(document.file_path)
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read image file"
        )

    # Detect edges
    corners = scanner.detect_document_edges(image)

    height, width = image.shape[:2]
    confidence = 0.0

    if corners is None:
        # Return full image corners as fallback
        corners = np.array(
            [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
            dtype=np.float32,
        )
        confidence = 0.0
    else:
        confidence = 0.85  # High confidence when edges detected

    # Create preview with corners drawn
    preview_path = os.path.join(
        os.path.dirname(document.file_path), f"preview_{document.stored_filename}"
    )

    preview = image.copy()
    pts = corners.astype(np.int32)
    cv2.polylines(preview, [pts], True, (0, 255, 0), 3)
    for pt in pts:
        cv2.circle(preview, tuple(pt), 10, (0, 0, 255), -1)

    cv2.imwrite(preview_path, preview)

    # Update document status
    document.status = "detected"

    return DetectResponse(
        document_uuid=document.uuid,
        corners=CornerPoints(
            top_left=corners[0].tolist(),
            top_right=corners[1].tolist(),
            bottom_right=corners[2].tolist(),
            bottom_left=corners[3].tolist(),
        ),
        confidence=confidence,
        preview_url=f"/api/documents/{document.uuid}/preview",
    )


@router.post("/process", response_model=ProcessResponse)
@limiter.limit(settings.rate_limit_process)
async def process_document(
    request_obj: Request,
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Process document with perspective transformation and enhancement.
    """
    result = await db.execute(
        select(Document).where(
            Document.uuid == request.document_uuid, Document.user_id == current_user.id
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

    # Load image
    image = cv2.imread(document.file_path)
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read image file"
        )

    # Get corners
    if request.corners:
        corners = np.array(
            [
                request.corners.top_left,
                request.corners.top_right,
                request.corners.bottom_right,
                request.corners.bottom_left,
            ],
            dtype=np.float32,
        )
    else:
        # Auto-detect corners
        corners = scanner.detect_document_edges(image)
        if corners is None:
            height, width = image.shape[:2]
            corners = np.array(
                [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                dtype=np.float32,
            )

    # Apply perspective transform
    warped = scanner.perspective_transform(image, corners)

    # Apply rotation if specified
    if request.settings.rotation > 0:
        warped = scanner.rotate_image(warped, request.settings.rotation)

    # Apply enhancement
    enhanced = scanner.enhance_scan(
        warped,
        mode=request.settings.filter_mode,
        brightness=request.settings.brightness,
        contrast=request.settings.contrast,
        auto_enhance=request.settings.auto_enhance,
    )

    # Save processed image
    processed_filename = f"processed_{document.stored_filename}"
    processed_path = os.path.join(
        os.path.dirname(document.file_path), processed_filename
    )
    cv2.imwrite(processed_path, enhanced, [cv2.IMWRITE_JPEG_QUALITY, 95])

    # Create thumbnail
    thumbnail = scanner.create_thumbnail(enhanced)
    thumbnail_filename = f"thumb_{document.stored_filename}"
    thumbnail_path = os.path.join(
        os.path.dirname(document.file_path), thumbnail_filename
    )
    cv2.imwrite(thumbnail_path, thumbnail)

    # Update document
    document.processed_path = processed_path
    document.thumbnail_path = thumbnail_path
    document.status = "completed"

    return ProcessResponse(
        document_uuid=document.uuid,
        processed_url=f"/api/documents/{document.uuid}/processed",
        thumbnail_url=f"/api/documents/{document.uuid}/thumbnail",
        status="completed",
    )


@router.post("/ocr/{document_uuid}", response_model=OCRResponse)
async def extract_text(
    document_uuid: str,
    lang: str = "eng+ind",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Extract text from document using OCR.
    """
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

    # Use processed image if available, otherwise original
    image_path = (
        document.processed_path if document.processed_path else document.file_path
    )

    if not os.path.exists(image_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    # Load image
    image = cv2.imread(image_path)
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Could not read image file"
        )

    # Extract text
    text, confidence = ocr_service.extract_text(image, lang)

    # Update document
    document.ocr_text = text

    return OCRResponse(
        document_uuid=document.uuid, text=text, confidence=confidence, language=lang
    )


@router.post("/export", response_model=ExportResponse)
async def export_documents(
    request: ExportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export documents as PDF, images, or ZIP.
    - pdf with merge_pdf=True: All pages merged into single PDF
    - pdf with merge_pdf=False: ZIP containing separate PDFs
    - zip: ZIP containing images (png/jpg based on quality)
    - png/jpg: Single image (only for single document)
    """
    # Get all requested documents
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

    # Sort documents to maintain order from request
    uuid_order = {uuid: idx for idx, uuid in enumerate(request.document_uuids)}
    documents.sort(key=lambda d: uuid_order.get(d.uuid, 999))

    # Get image paths (use processed if available)
    image_paths = []
    for doc in documents:
        path = doc.processed_path if doc.processed_path else doc.file_path
        if path and os.path.exists(path):
            image_paths.append((path, doc.original_filename))

    if not image_paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No valid images found"
        )

    # Generate export file
    export_dir = os.path.join(settings.upload_dir, str(current_user.uuid), "exports")
    os.makedirs(export_dir, exist_ok=True)

    export_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if request.format == "pdf":
        if request.merge_pdf:
            # Merge all into single PDF
            export_filename = f"docuscan_{timestamp}.pdf"
            export_path = os.path.join(export_dir, export_filename)

            if request.searchable:
                # Create searchable PDF with OCR text layer
                ocr_data = []
                for img_path, _ in image_paths:
                    image = cv2.imread(img_path)
                    if image is not None:
                        words = ocr_service.extract_text_with_boxes(image)
                        ocr_data.append(words)
                    else:
                        ocr_data.append([])

                pdf_service.create_searchable_pdf_from_images(
                    [p[0] for p in image_paths],
                    export_path,
                    ocr_data,
                    page_size=request.page_size,
                    quality=request.quality,
                )
            else:
                pdf_service.create_pdf_from_images(
                    [p[0] for p in image_paths],
                    export_path,
                    page_size=request.page_size,
                    quality=request.quality,
                )
        else:
            # Create ZIP with separate PDFs
            export_filename = f"docuscan_{timestamp}.zip"
            export_path = os.path.join(export_dir, export_filename)

            with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, (img_path, orig_name) in enumerate(image_paths, 1):
                    # Create individual PDF with sanitized filename
                    safe_name = sanitize_filename(orig_name)
                    base_name = os.path.splitext(safe_name)[0]
                    pdf_name = f"{base_name}.pdf"
                    temp_pdf = os.path.join(export_dir, f"temp_{export_id}_{idx}.pdf")
                    pdf_service.create_pdf_from_images(
                        [img_path],
                        temp_pdf,
                        page_size=request.page_size,
                        quality=request.quality,
                    )
                    zf.write(temp_pdf, pdf_name)
                    os.remove(temp_pdf)

    elif request.format == "zip":
        # ZIP with images
        export_filename = f"docuscan_{timestamp}.zip"
        export_path = os.path.join(export_dir, export_filename)

        img_ext = "jpg" if request.quality < 100 else "png"

        with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for idx, (img_path, orig_name) in enumerate(image_paths, 1):
                # Sanitize filename for archive entry
                safe_name = sanitize_filename(orig_name)
                base_name = os.path.splitext(safe_name)[0]

                # Read and re-encode image with quality settings
                image = cv2.imread(img_path)
                temp_img = os.path.join(export_dir, f"temp_{export_id}_{idx}.{img_ext}")

                if img_ext == "jpg":
                    cv2.imwrite(
                        temp_img, image, [cv2.IMWRITE_JPEG_QUALITY, request.quality]
                    )
                else:
                    cv2.imwrite(temp_img, image)

                zf.write(temp_img, f"{base_name}.{img_ext}")
                os.remove(temp_img)
    else:
        # For single image export (jpg/png)
        if len(image_paths) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Multiple images can only be exported as PDF or ZIP",
            )

        export_filename = f"docuscan_{timestamp}.{request.format}"
        export_path = os.path.join(export_dir, export_filename)

        image = cv2.imread(image_paths[0][0])
        if request.format == "jpg":
            cv2.imwrite(export_path, image, [cv2.IMWRITE_JPEG_QUALITY, request.quality])
        else:
            cv2.imwrite(
                export_path,
                image,
                [cv2.IMWRITE_PNG_COMPRESSION, 9 - request.quality // 12],
            )

    # Get file size
    file_size = os.path.getsize(export_path)

    # Set expiration
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.file_retention_minutes
    )

    return ExportResponse(
        download_url=f"/api/scan/download/{current_user.uuid}/{export_filename}",
        filename=export_filename,
        file_size=file_size,
        expires_at=expires_at,
    )


@router.get("/download/{user_uuid}/{filename}")
async def download_export(
    user_uuid: str, filename: str, current_user: User = Depends(get_current_user)
):
    """
    Download exported file.
    """
    if current_user.uuid != user_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied"
        )

    # Validate and sanitize filename to prevent path traversal
    safe_filename = sanitize_filename(filename)

    # Build safe path
    export_dir = os.path.join(settings.upload_dir, str(user_uuid), "exports")
    export_path = get_safe_path(export_dir, safe_filename)

    if not export_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename"
        )

    if not os.path.exists(export_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    # Determine media type
    if filename.endswith(".pdf"):
        media_type = "application/pdf"
    elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
        media_type = "image/jpeg"
    elif filename.endswith(".png"):
        media_type = "image/png"
    elif filename.endswith(".zip"):
        media_type = "application/zip"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        export_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/bulk-process", response_model=List[ProcessResponse])
@limiter.limit(settings.rate_limit_process)
async def bulk_process_documents(
    request_obj: Request,
    request: BulkProcessRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Process multiple documents in bulk.
    Each document can have its own corners and settings, or use defaults.
    """
    doc_uuids = [item.document_uuid for item in request.documents]

    result = await db.execute(
        select(Document).where(
            Document.uuid.in_(doc_uuids), Document.user_id == current_user.id
        )
    )
    documents = {doc.uuid: doc for doc in result.scalars().all()}

    responses = []

    for item in request.documents:
        document = documents.get(item.document_uuid)
        if not document or not os.path.exists(document.file_path):
            continue

        image = cv2.imread(document.file_path)
        if image is None:
            continue

        # Use item-specific settings or default
        doc_settings = item.settings or request.default_settings

        # Get corners (item-specific or auto-detect)
        if item.corners:
            corners = np.array(
                [
                    item.corners.top_left,
                    item.corners.top_right,
                    item.corners.bottom_right,
                    item.corners.bottom_left,
                ],
                dtype=np.float32,
            )
        else:
            corners = scanner.detect_document_edges(image)
            if corners is None:
                height, width = image.shape[:2]
                corners = np.array(
                    [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                    dtype=np.float32,
                )

        warped = scanner.perspective_transform(image, corners)

        if doc_settings.rotation > 0:
            warped = scanner.rotate_image(warped, doc_settings.rotation)

        enhanced = scanner.enhance_scan(
            warped,
            mode=doc_settings.filter_mode,
            brightness=doc_settings.brightness,
            contrast=doc_settings.contrast,
            auto_enhance=doc_settings.auto_enhance,
        )

        processed_filename = f"processed_{document.stored_filename}"
        processed_path = os.path.join(
            os.path.dirname(document.file_path), processed_filename
        )
        cv2.imwrite(processed_path, enhanced, [cv2.IMWRITE_JPEG_QUALITY, 95])

        thumbnail = scanner.create_thumbnail(enhanced)
        thumbnail_filename = f"thumb_{document.stored_filename}"
        thumbnail_path = os.path.join(
            os.path.dirname(document.file_path), thumbnail_filename
        )
        cv2.imwrite(thumbnail_path, thumbnail)

        document.processed_path = processed_path
        document.thumbnail_path = thumbnail_path
        document.status = "completed"

        responses.append(
            ProcessResponse(
                document_uuid=document.uuid,
                processed_url=f"/api/documents/{document.uuid}/processed",
                thumbnail_url=f"/api/documents/{document.uuid}/thumbnail",
                status="completed",
            )
        )

    return responses
