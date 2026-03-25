# AI Change Log

## 2026-03-25
- Added `backend/models.py`.
  - Introduced clean Pydantic schemas for `User`, `FormField`, and `Template`.
  - Added `FieldType` enum to constrain `field_type` values (`text`, `number`, `date`, `checkbox`).
  - Added `ImageDimension` nested schema for `original_dimension` (`width`, `height`).
  - Added `PyObjectId` and base Mongo model to support MongoDB `_id` and `owner_id` with Motor/Pydantic.
  - Added Motor collection helpers: `get_user_collection`, `get_template_collection`.
  - Added coordinate validation (`0-100`) and positive image dimension validation to avoid invalid template geometry.
- Updated popup extension implementation to align with backend integration.
  - Replaced starter counter UI in `entrypoints/popup/App.tsx` with FlashFill workflow UI.
  - Added `entrypoints/popup/types.ts` to mirror backend schemas for type-safe API usage.
  - Added `entrypoints/popup/api.ts` with reusable API client functions (`pingBackend`, `listTemplates`).
  - Refined popup styles in `entrypoints/popup/App.css` and `entrypoints/popup/style.css` for a clean, extension-focused layout.

## 2026-03-25 (scope correction)
- Reverted frontend popup integration changes to keep delivery backend-first only.
  - Restored starter files: `entrypoints/popup/App.tsx`, `entrypoints/popup/App.css`, `entrypoints/popup/style.css`.
  - Removed integration files: `entrypoints/popup/api.ts`, `entrypoints/popup/types.ts`.
  - Active functional scope is now backend schemas in `backend/models.py`.

## 2026-03-25 (production schema hardening)
- Updated `backend/models.py` for production-ready backend schema design.
  - Added `updated_at` for `User` and `Template` to support audit trails.
  - Added input normalization for email (`strip + lowercase`) via validators.
  - Added length constraints for `hashed_password`, `name`, `label`, and `image_hash`.
  - Added safe API DTOs: `UserCreate`, `UserPublic`, `TemplateCreate`, `TemplatePublic`.
  - Added `create_indexes(db)` async helper to create key MongoDB indexes:
    - unique `users.email`
    - `templates.owner_id`
    - `templates.image_hash`
    - compound `templates.owner_id + templates.image_hash`
    - `templates.is_public`

## 2026-03-25 (ocr core logic)
- Added OCR analyze API in `backend/main.py`:
  - `POST /api/v1/ocr/analyze` accepts `UploadFile` image input.
  - Validates MIME type and empty upload errors.
  - Returns typed OCR response model for frontend canvas rendering.
- Added image + OCR processing engine in `backend/ocr_engine.py`:
  - OpenCV pipeline: grayscale -> denoise -> deskew auto-rotation.
  - Google Cloud Vision integration using `document_text_detection`.
  - Extracts text blocks from `full_text_annotation.pages[].blocks[]`.
  - Converts all block polygon coordinates from pixels to percent values (`x_percent`, `y_percent`) based on original image width/height.
  - Returns both normalized polygon and normalized bbox (`x/y/w/h` in percent).
- Added backend Python dependency manifest in `backend/requirements.txt`.

## 2026-03-25 (lifecycle auth persistence)
- Updated `backend/main.py`:
  - Added FastAPI lifespan to initialize MongoDB client from `MONGODB_URI` and `MONGODB_DB`.
  - Calls `create_indexes(db)` on startup, closes Mongo client on shutdown.
  - Added JWT-protected OCR endpoint with dependency `get_current_user`.
  - Persists OCR result into Mongo `documents` collection and returns `document_id` + `image_hash`.
- Added `backend/auth.py`:
  - Implemented Bearer JWT validation using `python-jose`.
  - Parses user context from claims (`sub`/`user_id`, optional `email`, `is_premium`).
- Updated `backend/models.py`:
  - Added `DOCUMENTS_COLLECTION`, `get_document_collection`, and `OCRDocument` schema.
  - Added document indexes (`owner_id`, `image_hash`, `created_at`) in `create_indexes`.
- Updated `backend/requirements.txt`:
  - Added `python-jose[cryptography]` for JWT decode/verify.

## 2026-03-25 (template premium management)
- Added DB dependency module `backend/db.py`:
  - Introduced shared `get_database(request)` dependency for API modules.
- Updated `backend/auth.py`:
  - Added `ensure_premium_user(current_user, db)` DB-backed premium check.
  - Added `@premium_required` decorator to protect premium-only endpoints.
- Updated `backend/main.py`:
  - Added `GET /templates/library` (premium-only) returning public template library.
  - Added `POST /templates/save` to persist user-customized template layouts from extension.
  - Added template serializer for stable response model `TemplatePublic`.
- Updated `backend/models.py`:
  - Standardized `Template.owner_id` to string user identifier (aligned with JWT `sub`).

## 2026-03-25 (system boilerplate config)
- Updated `backend/main.py`:
  - Added `python-dotenv` loading via `load_dotenv()`.
  - Added CORS middleware for Chrome Extension origins using regex `^chrome-extension://.*$`.
  - Switched environment configuration to primary keys:
    - `MONGO_URI` (with fallback `MONGODB_URI`)
    - `MONGO_DB` (with fallback `MONGODB_DB`)
    - `GOOGLE_APPLICATION_CREDENTIALS`
- Updated `backend/auth.py`:
  - JWT secret now reads `JWT_SECRET` (fallback `JWT_SECRET_KEY` for compatibility).
- Updated `backend/requirements.txt`:
  - Added `python-dotenv` dependency.
- Added `backend/.env.example`:
  - Documents required environment variables for local and production setup.

## 2026-03-25 (production hardening pass)
- Updated `backend/auth.py`:
  - Fixed premium identity mapping by resolving JWT `sub` as ObjectId or string.
  - Premium DB check now uses robust `$or` lookup candidates (`_id` ObjectId, `_id` string, `email`).
- Updated `backend/main.py`:
  - Tightened CORS policy from wildcard Chrome extension regex to explicit allowlist origins.
  - Added env-driven CORS controls: `ALLOWED_EXTENSION_IDS`, `ALLOWED_WEB_ORIGINS`.
  - Added upload size limit (`MAX_UPLOAD_BYTES`) with chunked read and HTTP 413 handling.
  - Added `created_at` when persisting OCR documents to match schema consistency.
  - Replaced internal exception leak with server-side logging and generic 500 response.
  - Standardized template routes to API versioned paths:
    - `GET /api/v1/templates/library`
    - `POST /api/v1/templates/save`
- Updated `backend/.env.example`:
  - Added new production env variables for CORS allowlist and upload limits.

## 2026-03-25 (runtime setup and smoke test)
- Updated `package.json`:
  - Added backend run scripts:
    - `backend:dev` -> `python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000`
    - `backend:start` -> `python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000`
- Installed missing Python dependencies in active environment, including `email-validator`.
- Executed smoke tests with request samples via FastAPI TestClient (mocked DB/lifespan) for:
  - `GET /health`
  - `POST /api/v1/ocr/analyze`
  - `GET /api/v1/templates/library`
  - `POST /api/v1/templates/save`

## 2026-03-25 (api contract and error standardization)
- Updated `backend/main.py`:
  - Standardized error response format globally using exception handlers:
    - `HTTPException` -> `{ success: false, error: { code, message, details } }`
    - `RequestValidationError` -> same format with `validation_error`
    - unhandled exceptions -> same format with `internal_error`
  - Added `GET /api/v1/ocr/documents/{document_id}` endpoint.
    - Validates ObjectId format.
    - Enforces ownership (`owner_id` == current user).
    - Returns stored OCR payload for frontend re-fetch/render flow.
- Added `backend/API_OPENAPI_SUMMARY.md`:
  - OpenAPI-style concise documentation with sample requests and responses for frontend integration.
