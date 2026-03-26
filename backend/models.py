from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic_core import core_schema
from pymongo import ASCENDING


class PyObjectId(ObjectId):
    """Pydantic-compatible MongoDB ObjectId."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: Any,
    ) -> core_schema.CoreSchema:
        def validate(value: Any) -> ObjectId:
            if isinstance(value, ObjectId):
                return value
            if isinstance(value, str) and ObjectId.is_valid(value):
                return ObjectId(value)
            raise ValueError("Invalid ObjectId")

        return core_schema.no_info_plain_validator_function(validate)


class BaseMongoModel(BaseModel):
    """Base model with MongoDB alias support."""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


class User(BaseMongoModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    email: EmailStr
    hashed_password: str = Field(min_length=20, max_length=512)
    is_premium: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    is_premium: bool
    created_at: datetime
    updated_at: datetime


class FieldType(str, Enum):
    text = "text"
    number = "number"
    date = "date"
    checkbox = "checkbox"


class FormField(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    x: float = Field(ge=0.0, le=100.0)
    y: float = Field(ge=0.0, le=100.0)
    w: float = Field(gt=0.0, le=100.0)
    h: float = Field(gt=0.0, le=100.0)
    field_type: FieldType


class ImageDimension(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Template(BaseMongoModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    owner_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    image_hash: str = Field(min_length=16, max_length=128)
    original_dimension: ImageDimension
    fields: list[FormField] = Field(default_factory=list)
    is_public: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    image_hash: str = Field(min_length=16, max_length=128)
    original_dimension: ImageDimension
    fields: list[FormField] = Field(default_factory=list)
    is_public: bool = False


class TemplatePublic(BaseModel):
    id: str
    owner_id: str
    name: str
    image_hash: str
    original_dimension: ImageDimension
    fields: list[FormField]
    is_public: bool
    created_at: datetime
    updated_at: datetime


USERS_COLLECTION = "users"
TEMPLATES_COLLECTION = "templates"
DOCUMENTS_COLLECTION = "documents"


def get_user_collection(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    return db[USERS_COLLECTION]


def get_template_collection(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    return db[TEMPLATES_COLLECTION]


def get_document_collection(db: AsyncIOMotorDatabase) -> AsyncIOMotorCollection:
    return db[DOCUMENTS_COLLECTION]


class OCRDocument(BaseMongoModel):
    id: PyObjectId | None = Field(default=None, alias="_id")
    owner_id: str = Field(min_length=1, max_length=128)
    image_hash: str = Field(min_length=32, max_length=128)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    deskew_angle: float
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create required MongoDB indexes for production-safe queries."""

    user_collection = get_user_collection(db)
    template_collection = get_template_collection(db)
    document_collection = get_document_collection(db)

    await user_collection.create_index([("email", ASCENDING)], unique=True, name="uq_users_email")
    await template_collection.create_index([("owner_id", ASCENDING)], name="idx_templates_owner_id")
    await template_collection.create_index([("image_hash", ASCENDING)], name="idx_templates_image_hash")
    await template_collection.create_index(
        [("owner_id", ASCENDING), ("image_hash", ASCENDING)],
        name="idx_templates_owner_image_hash",
    )
    await template_collection.create_index([("is_public", ASCENDING)], name="idx_templates_is_public")
    await document_collection.create_index([("owner_id", ASCENDING)], name="idx_documents_owner_id")
    await document_collection.create_index([("image_hash", ASCENDING)], name="idx_documents_image_hash")
    await document_collection.create_index([("created_at", ASCENDING)], name="idx_documents_created_at")
