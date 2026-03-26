from __future__ import annotations

import hashlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .auth import AuthenticatedUser, get_current_user, premium_required
from .db import get_database
from .models import TemplateCreate, TemplatePublic, create_indexes, get_document_collection, get_template_collection
from .ocr_engine import OCRAnalyzeResponse, analyze_document


load_dotenv()
logger = logging.getLogger(__name__)


def _env(name: str, fallback: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is not None and value.strip():
        return value
    return fallback


def _parse_csv_env(name: str) -> list[str]:
    raw_value = _env(name, "")
    if raw_value is None:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _build_cors_origins() -> list[str]:
    extension_ids = _parse_csv_env("ALLOWED_EXTENSION_IDS")
    extension_origins = [f"chrome-extension://{extension_id}" for extension_id in extension_ids]
    web_origins = _parse_csv_env("ALLOWED_WEB_ORIGINS")
    return extension_origins + web_origins


class OCRAnalyzeAPIResponse(BaseModel):
    document_id: str
    image_hash: str = Field(min_length=32, max_length=128)
    ocr: OCRAnalyzeResponse


class OCRDocumentAPIResponse(BaseModel):
    document_id: str
    owner_id: str
    image_hash: str = Field(min_length=32, max_length=128)
    created_at: datetime
    ocr: OCRAnalyzeResponse


class APIError(BaseModel):
    code: str
    message: str
    details: Any | None = None


class APIErrorResponse(BaseModel):
    success: bool = False
    error: APIError


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_uri = _env("MONGO_URI", _env("MONGODB_URI", "mongodb://localhost:27017"))
    mongo_db_name = _env("MONGO_DB", _env("MONGODB_DB", "flashfill"))

    # Allow configuring Google Vision credentials path from .env.
    google_credentials = _env("GOOGLE_APPLICATION_CREDENTIALS")
    if google_credentials:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = google_credentials

    mongo_client = AsyncIOMotorClient(str(mongo_uri))
    mongo_db = mongo_client[mongo_db_name]

    await create_indexes(mongo_db)

    app.state.mongo_client = mongo_client
    app.state.mongo_db = mongo_db
    try:
        yield
    finally:
        mongo_client.close()


app = FastAPI(title="FlashFill Backend", version="0.1.0", lifespan=lifespan)

cors_origins = _build_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
) -> JSONResponse:
    payload = APIErrorResponse(error=APIError(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=payload.model_dump())


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        code = str(exc.detail.get("code", f"http_{exc.status_code}"))
        message = str(exc.detail.get("message", "Request failed"))
        details = exc.detail.get("details")
        return _error_response(exc.status_code, code, message, details)

    return _error_response(exc.status_code, f"http_{exc.status_code}", str(exc.detail), None)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(
        status_code=422,
        code="validation_error",
        message="Request validation failed",
        details=exc.errors(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server exception", exc_info=exc)
    return _error_response(500, "internal_error", "Internal server error", None)


def _serialize_template(template_doc: dict) -> TemplatePublic:
    return TemplatePublic(
        id=str(template_doc["_id"]),
        owner_id=str(template_doc["owner_id"]),
        name=template_doc["name"],
        image_hash=template_doc["image_hash"],
        original_dimension=template_doc["original_dimension"],
        fields=template_doc.get("fields", []),
        is_public=bool(template_doc.get("is_public", False)),
        created_at=template_doc["created_at"],
        updated_at=template_doc["updated_at"],
    )


def _serialize_ocr_document(doc: dict[str, Any]) -> OCRDocumentAPIResponse:
    ocr = OCRAnalyzeResponse(
        image_width=int(doc["image_width"]),
        image_height=int(doc["image_height"]),
        deskew_angle=float(doc["deskew_angle"]),
        blocks=doc.get("blocks", []),
    )
    return OCRDocumentAPIResponse(
        document_id=str(doc["_id"]),
        owner_id=str(doc["owner_id"]),
        image_hash=doc["image_hash"],
        created_at=doc["created_at"],
        ocr=ocr,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/ocr/analyze", response_model=OCRAnalyzeAPIResponse)
async def analyze_ocr(
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> OCRAnalyzeAPIResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    max_upload_bytes = int(_env("MAX_UPLOAD_BYTES", "10485760") or "10485760")
    chunks: list[bytes] = []
    total_size = 0

    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_upload_bytes:
            raise HTTPException(status_code=413, detail="Uploaded file exceeds size limit")
        chunks.append(chunk)

    content = b"".join(chunks)
    if not content:
        raise HTTPException(
            status_code=400,
            detail={"code": "empty_upload", "message": "Uploaded file is empty"},
        )

    try:
        ocr_result = await analyze_document(content)
        image_hash = hashlib.sha256(content).hexdigest()

        documents = get_document_collection(db)
        document_payload = {
            "owner_id": current_user.user_id,
            "image_hash": image_hash,
            "image_width": ocr_result.image_width,
            "image_height": ocr_result.image_height,
            "deskew_angle": ocr_result.deskew_angle,
            "blocks": [block.model_dump() for block in ocr_result.blocks],
            "created_at": datetime.now(timezone.utc),
        }
        inserted = await documents.insert_one(document_payload)

        return OCRAnalyzeAPIResponse(
            document_id=str(inserted.inserted_id),
            image_hash=image_hash,
            ocr=ocr_result,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_image", "message": str(exc)},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "vision_api_error", "message": f"Vision API error: {exc}"},
        ) from exc
    except Exception as exc:
        logger.exception("Unhandled OCR processing error")
        raise HTTPException(
            status_code=500,
            detail={"code": "ocr_internal_error", "message": "Internal OCR error"},
        ) from exc


@app.get("/api/v1/ocr/documents/{document_id}", response_model=OCRDocumentAPIResponse)
async def get_ocr_document(
    document_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> OCRDocumentAPIResponse:
    if not ObjectId.is_valid(document_id):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_document_id", "message": "Invalid document id"},
        )

    documents = get_document_collection(db)
    doc = await documents.find_one({"_id": ObjectId(document_id), "owner_id": current_user.user_id})
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "document_not_found", "message": "OCR document not found"},
        )

    return _serialize_ocr_document(doc)


@app.get("/api/v1/templates/library", response_model=list[TemplatePublic])
@premium_required
async def get_template_library(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> list[TemplatePublic]:
    templates = get_template_collection(db)
    cursor = templates.find({"is_public": True}).sort("updated_at", -1)
    template_docs = await cursor.to_list(length=200)
    return [_serialize_template(doc) for doc in template_docs]


@app.post("/api/v1/templates/save", response_model=TemplatePublic)
async def save_template(
    payload: TemplateCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> TemplatePublic:
    now = datetime.now(timezone.utc)
    template_doc = {
        "owner_id": current_user.user_id,
        "name": payload.name,
        "image_hash": payload.image_hash,
        "original_dimension": payload.original_dimension.model_dump(),
        "fields": [field.model_dump() for field in payload.fields],
        "is_public": False,
        "created_at": now,
        "updated_at": now,
    }

    templates = get_template_collection(db)
    inserted = await templates.insert_one(template_doc)
    template_doc["_id"] = inserted.inserted_id

    return _serialize_template(template_doc)
