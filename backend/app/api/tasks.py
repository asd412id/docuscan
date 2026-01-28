"""
API endpoints for background task management.
Provides endpoints to start background tasks and check their status.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
import json

from app.database import get_db
from app.config import get_settings
from app.models.models import User, Document
from app.api.auth import get_current_user
from app.schemas.schemas import (
    CornerPoints,
    ScanSettings,
    BulkProcessRequest,
)

router = APIRouter()
settings = get_settings()


# Request/Response schemas for background tasks
class BackgroundTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    current: int = 0
    total: int = 0
    percentage: int = 0
    message: str = ""
    result: Optional[dict] = None


class BulkProcessBackgroundRequest(BaseModel):
    documents: List[dict]  # List of {document_uuid, corners?, settings?}
    default_settings: Optional[ScanSettings] = None


def get_celery_app():
    """Get Celery app, raise error if not enabled."""
    if not settings.celery_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background processing not available. Set CELERY_ENABLED=true",
        )
    from app.celery_app import celery_app

    return celery_app


def get_redis_client():
    """Get Redis client for progress checking."""
    import redis

    return redis.from_url(settings.redis_url)


@router.post("/process/{document_uuid}", response_model=BackgroundTaskResponse)
async def start_process_task(
    document_uuid: str,
    corners: Optional[CornerPoints] = None,
    settings_data: Optional[ScanSettings] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start background processing for a single document.
    Returns task_id for tracking progress.
    """
    celery_app = get_celery_app()

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

    # Prepare corners dict
    corners_dict = None
    if corners:
        corners_dict = {
            "top_left": corners.top_left,
            "top_right": corners.top_right,
            "bottom_right": corners.bottom_right,
            "bottom_left": corners.bottom_left,
        }

    # Prepare settings dict
    settings_dict = None
    if settings_data:
        settings_dict = {
            "filter_mode": settings_data.filter_mode,
            "brightness": settings_data.brightness,
            "contrast": settings_data.contrast,
            "rotation": settings_data.rotation,
            "auto_enhance": settings_data.auto_enhance,
        }

    # Start Celery task
    from app.tasks.processing import process_single_document

    task = process_single_document.delay(
        document_uuid=document.uuid,
        file_path=document.file_path,
        stored_filename=document.stored_filename,
        corners=corners_dict,
        settings_dict=settings_dict,
    )

    return BackgroundTaskResponse(
        task_id=task.id, status="started", message="Processing started in background"
    )


@router.post("/bulk-process", response_model=BackgroundTaskResponse)
async def start_bulk_process_task(
    request: BulkProcessBackgroundRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start background processing for multiple documents.
    Returns task_id for tracking overall progress.
    """
    celery_app = get_celery_app()

    doc_uuids = [item["document_uuid"] for item in request.documents]

    result = await db.execute(
        select(Document).where(
            Document.uuid.in_(doc_uuids), Document.user_id == current_user.id
        )
    )
    documents = {doc.uuid: doc for doc in result.scalars().all()}

    # Build document list for task
    doc_list = []
    for item in request.documents:
        doc = documents.get(item["document_uuid"])
        if not doc:
            continue

        doc_data = {
            "uuid": doc.uuid,
            "file_path": doc.file_path,
            "stored_filename": doc.stored_filename,
        }

        # Add corners if provided
        if "corners" in item and item["corners"]:
            doc_data["corners"] = item["corners"]

        # Add settings if provided
        if "settings" in item and item["settings"]:
            doc_data["settings"] = item["settings"]

        doc_list.append(doc_data)

    if not doc_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No valid documents found"
        )

    # Prepare default settings
    default_settings = None
    if request.default_settings:
        default_settings = {
            "filter_mode": request.default_settings.filter_mode,
            "brightness": request.default_settings.brightness,
            "contrast": request.default_settings.contrast,
            "rotation": request.default_settings.rotation,
            "auto_enhance": request.default_settings.auto_enhance,
        }

    # Start Celery task
    from app.tasks.processing import process_bulk_documents

    task = process_bulk_documents.delay(
        documents=doc_list,
        default_settings=default_settings,
    )

    return BackgroundTaskResponse(
        task_id=task.id,
        status="started",
        message=f"Started processing {len(doc_list)} documents in background",
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the status and progress of a background task.
    """
    celery_app = get_celery_app()

    # First check Redis for progress info
    try:
        redis_client = get_redis_client()
        progress_data = redis_client.get(f"task_progress:{task_id}")

        if progress_data:
            progress = json.loads(progress_data)
            # Also get Celery task result if completed
            task_result = celery_app.AsyncResult(task_id)
            result = None
            if task_result.ready():
                result = task_result.result

            return TaskStatusResponse(
                task_id=task_id,
                status=progress.get("status", "unknown"),
                current=progress.get("current", 0),
                total=progress.get("total", 0),
                percentage=progress.get("percentage", 0),
                message=progress.get("message", ""),
                result=result if isinstance(result, dict) else None,
            )
    except Exception:
        pass

    # Fallback to Celery task state
    task_result = celery_app.AsyncResult(task_id)

    status_map = {
        "PENDING": "pending",
        "STARTED": "processing",
        "SUCCESS": "completed",
        "FAILURE": "failed",
        "RETRY": "retrying",
        "REVOKED": "cancelled",
    }

    task_status = status_map.get(task_result.state, "unknown")

    result = None
    if task_result.ready():
        result = task_result.result
        if isinstance(result, Exception):
            result = {"error": str(result)}

    return TaskStatusResponse(
        task_id=task_id,
        status=task_status,
        current=100 if task_status == "completed" else 0,
        total=100,
        percentage=100 if task_status == "completed" else 0,
        message=f"Task {task_status}",
        result=result if isinstance(result, dict) else None,
    )


@router.post("/cancel/{task_id}")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Cancel a running background task.
    """
    celery_app = get_celery_app()

    celery_app.control.revoke(task_id, terminate=True)

    return {
        "task_id": task_id,
        "status": "cancelled",
        "message": "Task cancellation requested",
    }


@router.post("/complete/{task_id}")
async def apply_task_results(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Apply the results of a completed task to the database.
    This updates document statuses and paths after background processing.
    """
    celery_app = get_celery_app()

    task_result = celery_app.AsyncResult(task_id)

    if not task_result.ready():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Task not yet completed"
        )

    result = task_result.result

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task result"
        )

    # Handle single document result
    if "document_uuid" in result and "processed_path" in result:
        doc_result = await db.execute(
            select(Document).where(
                Document.uuid == result["document_uuid"],
                Document.user_id == current_user.id,
            )
        )
        document = doc_result.scalar_one_or_none()

        if document:
            document.processed_path = result["processed_path"]
            document.thumbnail_path = result.get("thumbnail_path")
            document.status = "completed"
            await db.commit()

        return {"status": "applied", "documents_updated": 1}

    # Handle bulk processing result
    if "results" in result:
        updated = 0
        for doc_result in result["results"]:
            if doc_result.get("status") != "completed":
                continue

            db_result = await db.execute(
                select(Document).where(
                    Document.uuid == doc_result["document_uuid"],
                    Document.user_id == current_user.id,
                )
            )
            document = db_result.scalar_one_or_none()

            if document:
                document.processed_path = doc_result["processed_path"]
                document.thumbnail_path = doc_result.get("thumbnail_path")
                document.status = "completed"
                updated += 1

        await db.commit()
        return {"status": "applied", "documents_updated": updated}

    return {"status": "no_changes", "documents_updated": 0}
