"""
Background processing tasks for document scanning operations.
These tasks run asynchronously via Celery workers.
"""

import os
import json
import cv2
import numpy as np
import logging
from celery import shared_task
from typing import Optional, List, Dict, Any
import redis

from app.config import get_settings
from app.services.scanner_service import scanner
from app.services.ocr_service import ocr_service
from app.services.pdf_service import pdf_service

settings = get_settings()
logger = logging.getLogger(__name__)

# Redis client for progress updates
_redis_client = None


def get_redis_client():
    """Get or create Redis client for progress updates."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url)
    return _redis_client


def update_task_progress(
    task_id: str,
    current: int,
    total: int,
    status: str = "processing",
    message: str = "",
):
    """Update task progress in Redis for real-time tracking."""
    try:
        client = get_redis_client()
        progress_data = {
            "task_id": task_id,
            "current": current,
            "total": total,
            "percentage": round((current / total) * 100) if total > 0 else 0,
            "status": status,
            "message": message,
        }
        # Store progress with 1 hour expiry
        client.setex(f"task_progress:{task_id}", 3600, json.dumps(progress_data))
        # Publish to channel for real-time updates
        client.publish(f"task_updates:{task_id}", json.dumps(progress_data))
    except Exception as e:
        logger.error(f"Failed to update progress: {e}")


@shared_task(bind=True, name="process_single_document")
def process_single_document(
    self,
    document_uuid: str,
    file_path: str,
    stored_filename: str,
    corners: Optional[Dict[str, List[float]]] = None,
    settings_dict: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process a single document with perspective transformation and enhancement.

    Args:
        document_uuid: UUID of the document
        file_path: Path to the original image file
        stored_filename: Stored filename for generating output paths
        corners: Optional corner points for perspective transform
        settings_dict: Processing settings (filter_mode, brightness, contrast, etc.)

    Returns:
        Dict with processed_path, thumbnail_path, and status
    """
    task_id = self.request.id
    update_task_progress(task_id, 0, 100, "processing", "Loading image...")

    try:
        # Load image
        image = cv2.imread(file_path)
        if image is None:
            return {"status": "failed", "error": "Could not read image file"}

        update_task_progress(task_id, 20, 100, "processing", "Detecting edges...")

        # Get corners
        if corners:
            corner_array = np.array(
                [
                    corners["top_left"],
                    corners["top_right"],
                    corners["bottom_right"],
                    corners["bottom_left"],
                ],
                dtype=np.float32,
            )
        else:
            corner_array = scanner.detect_document_edges(image)
            if corner_array is None:
                height, width = image.shape[:2]
                corner_array = np.array(
                    [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                    dtype=np.float32,
                )

        update_task_progress(
            task_id, 40, 100, "processing", "Applying perspective transform..."
        )

        # Apply perspective transform
        warped = scanner.perspective_transform(image, corner_array)

        # Apply settings
        if settings_dict:
            rotation = settings_dict.get("rotation", 0)
            if rotation > 0:
                warped = scanner.rotate_image(warped, rotation)

            update_task_progress(task_id, 60, 100, "processing", "Enhancing image...")

            enhanced = scanner.enhance_scan(
                warped,
                mode=settings_dict.get("filter_mode", "color"),
                brightness=settings_dict.get("brightness", 0),
                contrast=settings_dict.get("contrast", 0),
                auto_enhance=settings_dict.get("auto_enhance", False),
            )
        else:
            enhanced = warped

        update_task_progress(
            task_id, 80, 100, "processing", "Saving processed image..."
        )

        # Save processed image
        processed_filename = f"processed_{stored_filename}"
        processed_path = os.path.join(os.path.dirname(file_path), processed_filename)
        if not cv2.imwrite(processed_path, enhanced, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            return {"status": "failed", "error": "Failed to write processed image"}

        # Create thumbnail
        thumbnail = scanner.create_thumbnail(enhanced)
        thumbnail_filename = f"thumb_{stored_filename}"
        thumbnail_path = os.path.join(os.path.dirname(file_path), thumbnail_filename)
        if not cv2.imwrite(thumbnail_path, thumbnail):
            return {"status": "failed", "error": "Failed to write thumbnail image"}

        update_task_progress(task_id, 100, 100, "completed", "Processing complete")

        return {
            "status": "completed",
            "document_uuid": document_uuid,
            "processed_path": processed_path,
            "thumbnail_path": thumbnail_path,
        }

    except Exception as e:
        update_task_progress(task_id, 0, 100, "failed", str(e))
        return {"status": "failed", "error": str(e)}


@shared_task(bind=True, name="process_bulk_documents")
def process_bulk_documents(
    self,
    documents: List[Dict[str, Any]],
    default_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process multiple documents in bulk as a background task.

    Args:
        documents: List of document dicts with uuid, file_path, stored_filename, corners, settings
        default_settings: Default settings to use if document doesn't have specific settings

    Returns:
        Dict with results list and overall status
    """
    task_id = self.request.id
    total = len(documents)
    results = []

    update_task_progress(
        task_id,
        0,
        total,
        "processing",
        f"Starting bulk processing of {total} documents...",
    )

    for idx, doc in enumerate(documents):
        try:
            # Load image
            image = cv2.imread(doc["file_path"])
            if image is None:
                results.append(
                    {
                        "document_uuid": doc["uuid"],
                        "status": "failed",
                        "error": "Could not read image file",
                    }
                )
                continue

            # Get corners
            corners = doc.get("corners")
            if corners:
                corner_array = np.array(
                    [
                        corners["top_left"],
                        corners["top_right"],
                        corners["bottom_right"],
                        corners["bottom_left"],
                    ],
                    dtype=np.float32,
                )
            else:
                corner_array = scanner.detect_document_edges(image)
                if corner_array is None:
                    height, width = image.shape[:2]
                    corner_array = np.array(
                        [
                            [0, 0],
                            [width - 1, 0],
                            [width - 1, height - 1],
                            [0, height - 1],
                        ],
                        dtype=np.float32,
                    )

            # Apply perspective transform
            warped = scanner.perspective_transform(image, corner_array)

            # Get settings (document-specific or default)
            doc_settings = doc.get("settings") or default_settings or {}

            rotation = doc_settings.get("rotation", 0)
            if rotation > 0:
                warped = scanner.rotate_image(warped, rotation)

            enhanced = scanner.enhance_scan(
                warped,
                mode=doc_settings.get("filter_mode", "color"),
                brightness=doc_settings.get("brightness", 0),
                contrast=doc_settings.get("contrast", 0),
                auto_enhance=doc_settings.get("auto_enhance", False),
            )

            # Save processed image
            processed_filename = f"processed_{doc['stored_filename']}"
            processed_path = os.path.join(
                os.path.dirname(doc["file_path"]), processed_filename
            )
            if not cv2.imwrite(
                processed_path, enhanced, [cv2.IMWRITE_JPEG_QUALITY, 95]
            ):
                results.append(
                    {
                        "document_uuid": doc["uuid"],
                        "status": "failed",
                        "error": "Failed to write processed image",
                    }
                )
                continue

            # Create thumbnail
            thumbnail = scanner.create_thumbnail(enhanced)
            thumbnail_filename = f"thumb_{doc['stored_filename']}"
            thumbnail_path = os.path.join(
                os.path.dirname(doc["file_path"]), thumbnail_filename
            )
            if not cv2.imwrite(thumbnail_path, thumbnail):
                results.append(
                    {
                        "document_uuid": doc["uuid"],
                        "status": "failed",
                        "error": "Failed to write thumbnail image",
                    }
                )
                continue

            results.append(
                {
                    "document_uuid": doc["uuid"],
                    "status": "completed",
                    "processed_path": processed_path,
                    "thumbnail_path": thumbnail_path,
                }
            )

        except Exception as e:
            results.append(
                {"document_uuid": doc["uuid"], "status": "failed", "error": str(e)}
            )

        # Update progress
        update_task_progress(
            task_id,
            idx + 1,
            total,
            "processing",
            f"Processed {idx + 1}/{total} documents",
        )

    # Final status
    successful = sum(1 for r in results if r["status"] == "completed")
    final_status = (
        "completed"
        if successful == total
        else "partial"
        if successful > 0
        else "failed"
    )

    update_task_progress(
        task_id,
        total,
        total,
        final_status,
        f"Completed: {successful}/{total} documents processed successfully",
    )

    return {
        "status": final_status,
        "total": total,
        "successful": successful,
        "results": results,
    }


@shared_task(bind=True, name="extract_text_ocr")
def extract_text_ocr(
    self,
    document_uuid: str,
    image_path: str,
    language: str = "eng+ind",
) -> Dict[str, Any]:
    """
    Extract text from document using OCR as a background task.

    Args:
        document_uuid: UUID of the document
        image_path: Path to the image file
        language: Tesseract language code

    Returns:
        Dict with extracted text and confidence
    """
    task_id = self.request.id
    update_task_progress(task_id, 0, 100, "processing", "Loading image for OCR...")

    try:
        image = cv2.imread(image_path)
        if image is None:
            return {"status": "failed", "error": "Could not read image file"}

        update_task_progress(task_id, 30, 100, "processing", "Extracting text...")

        text, confidence = ocr_service.extract_text(image, language)

        update_task_progress(task_id, 100, 100, "completed", "Text extraction complete")

        return {
            "status": "completed",
            "document_uuid": document_uuid,
            "text": text,
            "confidence": confidence,
            "language": language,
        }

    except Exception as e:
        update_task_progress(task_id, 0, 100, "failed", str(e))
        return {"status": "failed", "error": str(e)}


@shared_task(bind=True, name="export_documents_task")
def export_documents_task(
    self,
    user_uuid: str,
    image_paths: List[tuple],  # List of (path, original_filename)
    export_format: str,
    export_dir: str,
    export_id: str,
    timestamp: str,
    quality: int = 90,
    page_size: str = "auto",
    merge_pdf: bool = True,
    searchable: bool = False,
) -> Dict[str, Any]:
    """
    Export documents as PDF, images, or ZIP as a background task.

    Args:
        user_uuid: User's UUID
        image_paths: List of (path, original_filename) tuples
        export_format: pdf, zip, jpg, or png
        export_dir: Directory to save exports
        export_id: Unique export ID
        timestamp: Timestamp string for filename
        quality: Image quality (1-100)
        page_size: PDF page size (auto, a4, letter)
        merge_pdf: Whether to merge PDFs
        searchable: Whether to create searchable PDF

    Returns:
        Dict with export file path and status
    """
    import zipfile

    task_id = self.request.id
    total_files = len(image_paths)

    update_task_progress(task_id, 0, total_files, "processing", "Starting export...")

    try:
        os.makedirs(export_dir, exist_ok=True)

        if export_format == "pdf":
            if merge_pdf:
                export_filename = f"docuscan_{timestamp}.pdf"
                export_path = os.path.join(export_dir, export_filename)

                if searchable:
                    update_task_progress(
                        task_id,
                        0,
                        total_files,
                        "processing",
                        "Running OCR for searchable PDF...",
                    )

                    ocr_data = []
                    for idx, (img_path, _) in enumerate(image_paths):
                        image = cv2.imread(img_path)
                        if image is not None:
                            words = ocr_service.extract_text_with_boxes(image)
                            ocr_data.append(words)
                        else:
                            ocr_data.append([])
                        update_task_progress(
                            task_id,
                            idx + 1,
                            total_files * 2,
                            "processing",
                            f"OCR: {idx + 1}/{total_files}",
                        )

                    update_task_progress(
                        task_id,
                        total_files,
                        total_files * 2,
                        "processing",
                        "Creating searchable PDF...",
                    )

                    pdf_service.create_searchable_pdf_from_images(
                        [p[0] for p in image_paths],
                        export_path,
                        ocr_data,
                        page_size=page_size,
                        quality=quality,
                    )
                else:
                    update_task_progress(task_id, 0, 1, "processing", "Creating PDF...")
                    pdf_service.create_pdf_from_images(
                        [p[0] for p in image_paths],
                        export_path,
                        page_size=page_size,
                        quality=quality,
                    )
            else:
                export_filename = f"docuscan_{timestamp}.zip"
                export_path = os.path.join(export_dir, export_filename)

                with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for idx, (img_path, orig_name) in enumerate(image_paths):
                        from app.utils.security import sanitize_filename

                        safe_name = sanitize_filename(orig_name)
                        base_name = os.path.splitext(safe_name)[0]
                        pdf_name = f"{base_name}.pdf"
                        temp_pdf = os.path.join(
                            export_dir, f"temp_{export_id}_{idx}.pdf"
                        )
                        pdf_service.create_pdf_from_images(
                            [img_path], temp_pdf, page_size=page_size, quality=quality
                        )
                        zf.write(temp_pdf, pdf_name)
                        os.remove(temp_pdf)
                        update_task_progress(
                            task_id,
                            idx + 1,
                            total_files,
                            "processing",
                            f"Created PDF {idx + 1}/{total_files}",
                        )

        elif export_format == "zip":
            export_filename = f"docuscan_{timestamp}.zip"
            export_path = os.path.join(export_dir, export_filename)
            img_ext = "jpg" if quality < 100 else "png"

            with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, (img_path, orig_name) in enumerate(image_paths):
                    from app.utils.security import sanitize_filename

                    safe_name = sanitize_filename(orig_name)
                    base_name = os.path.splitext(safe_name)[0]

                    image = cv2.imread(img_path)
                    temp_img = os.path.join(
                        export_dir, f"temp_{export_id}_{idx}.{img_ext}"
                    )

                    if img_ext == "jpg":
                        cv2.imwrite(
                            temp_img, image, [cv2.IMWRITE_JPEG_QUALITY, quality]
                        )
                    else:
                        cv2.imwrite(temp_img, image)

                    zf.write(temp_img, f"{base_name}.{img_ext}")
                    os.remove(temp_img)
                    update_task_progress(
                        task_id,
                        idx + 1,
                        total_files,
                        "processing",
                        f"Added {idx + 1}/{total_files} images",
                    )

        else:
            # Single image export
            export_filename = f"docuscan_{timestamp}.{export_format}"
            export_path = os.path.join(export_dir, export_filename)

            image = cv2.imread(image_paths[0][0])
            if export_format == "jpg":
                cv2.imwrite(export_path, image, [cv2.IMWRITE_JPEG_QUALITY, quality])
            else:
                cv2.imwrite(
                    export_path, image, [cv2.IMWRITE_PNG_COMPRESSION, 9 - quality // 12]
                )

        file_size = os.path.getsize(export_path)

        update_task_progress(
            task_id, total_files, total_files, "completed", "Export complete"
        )

        return {
            "status": "completed",
            "export_path": export_path,
            "filename": export_filename,
            "file_size": file_size,
            "download_url": f"/api/scan/download/{user_uuid}/{export_filename}",
        }

    except Exception as e:
        update_task_progress(task_id, 0, total_files, "failed", str(e))
        return {"status": "failed", "error": str(e)}
