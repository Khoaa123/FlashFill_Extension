from __future__ import annotations

import inspect
import os
from functools import wraps
from typing import Any, Awaitable, Callable

from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, EmailStr, Field

from .models import get_user_collection


bearer_scheme = HTTPBearer(auto_error=True)


class AuthenticatedUser(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    email: EmailStr | None = None
    is_premium: bool = False


def _jwt_secret_key() -> str:
    secret = os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET is not configured",
        )
    return secret


def _jwt_algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256")


def _decode_token(token: str) -> AuthenticatedUser:
    try:
        payload = jwt.decode(token, _jwt_secret_key(), algorithms=[_jwt_algorithm()])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    user_id = payload.get("sub") or payload.get("user_id")
    if not user_id or not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing subject",
        )

    email = payload.get("email")
    if email is not None and not isinstance(email, str):
        email = None

    is_premium = bool(payload.get("is_premium", False))
    return AuthenticatedUser(user_id=user_id, email=email, is_premium=is_premium)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthenticatedUser:
    return _decode_token(credentials.credentials)


def _build_user_lookup_candidates(current_user: AuthenticatedUser) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    if ObjectId.is_valid(current_user.user_id):
        candidates.append({"_id": ObjectId(current_user.user_id)})

    candidates.append({"_id": current_user.user_id})

    if current_user.email:
        candidates.append({"email": current_user.email.lower()})

    return candidates


async def ensure_premium_user(current_user: AuthenticatedUser, db: AsyncIOMotorDatabase) -> None:
    users = get_user_collection(db)
    user_doc = await users.find_one(
        {"$or": _build_user_lookup_candidates(current_user)},
        {"is_premium": 1},
    )

    if not user_doc or not bool(user_doc.get("is_premium", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium subscription is required",
        )


def premium_required(
    endpoint: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    @wraps(endpoint)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        current_user: AuthenticatedUser | None = kwargs.get("current_user")
        db: AsyncIOMotorDatabase | None = kwargs.get("db")

        if current_user is None or db is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="premium_required decorator requires current_user and db dependencies",
            )

        await ensure_premium_user(current_user, db)
        return await endpoint(*args, **kwargs)

    wrapper.__signature__ = inspect.signature(endpoint)
    return wrapper
