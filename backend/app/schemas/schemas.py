from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# ============ User Schemas ============
class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100)


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6, max_length=100)


# ============ Token Schemas ============
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenWithRefresh(BaseModel):
    """Token response that includes refresh token (for backward compatibility only)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None
    scopes: List[str] = []


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ============ Document Schemas ============
class DocumentBase(BaseModel):
    original_filename: str


class DocumentResponse(DocumentBase):
    id: int
    uuid: str
    stored_filename: str
    file_size: int
    mime_type: str
    status: str
    created_at: datetime
    thumbnail_url: Optional[str] = None
    processed_url: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int
    page: int
    page_size: int


# ============ Scan Schemas ============
class CornerPoints(BaseModel):
    top_left: List[float] = Field(..., min_length=2, max_length=2)
    top_right: List[float] = Field(..., min_length=2, max_length=2)
    bottom_right: List[float] = Field(..., min_length=2, max_length=2)
    bottom_left: List[float] = Field(..., min_length=2, max_length=2)


class ScanSettings(BaseModel):
    filter_mode: str = Field(default="color", pattern="^(color|grayscale|bw|scan)$")
    brightness: float = Field(default=0, ge=-100, le=100)
    contrast: float = Field(default=0, ge=-100, le=100)
    rotation: int = Field(default=0, ge=0, le=360)
    auto_enhance: bool = True


class ProcessRequest(BaseModel):
    document_uuid: str
    corners: Optional[CornerPoints] = None
    settings: ScanSettings = ScanSettings()


class BulkProcessItem(BaseModel):
    document_uuid: str
    corners: Optional[CornerPoints] = None
    settings: Optional[ScanSettings] = None  # If None, use default settings


class BulkProcessRequest(BaseModel):
    documents: List[BulkProcessItem]
    default_settings: ScanSettings = ScanSettings()


class DetectResponse(BaseModel):
    document_uuid: str
    corners: CornerPoints
    confidence: float
    preview_url: str


class ProcessResponse(BaseModel):
    document_uuid: str
    processed_url: str
    thumbnail_url: str
    status: str


class BulkProcessResultItem(BaseModel):
    """Individual result for bulk processing with error details."""

    document_uuid: str
    success: bool
    processed_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: str
    error: Optional[str] = None


class BulkProcessResponse(BaseModel):
    """Response for bulk document processing with error reporting."""

    results: List[BulkProcessResultItem]
    total_requested: int
    successful: int
    failed: int


class OCRResponse(BaseModel):
    document_uuid: str
    text: str
    confidence: float
    language: str


class ExportRequest(BaseModel):
    document_uuids: List[str]
    format: str = Field(default="pdf", pattern="^(pdf|png|jpg|zip)$")
    quality: int = Field(default=90, ge=10, le=100)
    merge_pdf: bool = Field(
        default=True
    )  # For PDF: merge into one or zip separate files
    page_size: str = Field(
        default="auto", pattern="^(auto|a4|letter|legal|folio|f4)$"
    )  # PDF page size: auto=match image, a4, letter, legal, folio/f4
    searchable: bool = Field(
        default=False
    )  # For PDF: add invisible OCR text layer for searchability


class ExportResponse(BaseModel):
    download_url: str
    filename: str
    file_size: int
    expires_at: datetime


# ============ API Response Schemas ============
class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str


class BatchDeleteRequest(BaseModel):
    document_uuids: List[str] = Field(..., min_length=1, max_length=100)
