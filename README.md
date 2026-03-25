
# FlashFill Extension

Backend service for OCR processing and template management for the FlashFill browser extension.

## Current Scope

- FastAPI backend under [backend/main.py](backend/main.py)
- MongoDB persistence for users, OCR documents, and templates
- OCR pipeline via Google Vision in [backend/ocr_engine.py](backend/ocr_engine.py)
- JWT-protected APIs with premium gate for template library
- Standardized JSON error format

## Project Structure

- [backend/main.py](backend/main.py): app startup, middleware, exception handlers, and API routes
- [backend/auth.py](backend/auth.py): JWT decoding, current user dependency, premium guard
- [backend/models.py](backend/models.py): Pydantic models, Mongo collections, index creation
- [backend/db.py](backend/db.py): FastAPI dependency for database access
- [backend/ocr_engine.py](backend/ocr_engine.py): image preprocessing and OCR extraction
- [backend/API_OPENAPI_SUMMARY.md](backend/API_OPENAPI_SUMMARY.md): frontend-facing API summary
- [backend/.env.example](backend/.env.example): required environment configuration

## Requirements

- Python 3.10+
- MongoDB instance
- Google Cloud Vision credentials JSON

Install backend dependencies:

```bash
cd backend
pip install -r requirements.txt
```

Main backend dependencies are defined in [backend/requirements.txt](backend/requirements.txt), including FastAPI, Uvicorn, Motor, OpenCV, and Google Vision client.

## Environment Variables

Create backend env file from [backend/.env.example](backend/.env.example):

```bash
cd backend
copy .env.example .env
```

Variables:

- MONGO_URI: Mongo connection string, default mongodb://localhost:27017
- MONGO_DB: Database name, default flashfill
- GOOGLE_APPLICATION_CREDENTIALS: absolute path to Google service account JSON
- JWT_SECRET: secret used to verify JWT
- JWT_ALGORITHM: default HS256
- ALLOWED_EXTENSION_IDS: comma-separated Chrome extension IDs
- ALLOWED_WEB_ORIGINS: comma-separated web origins for CORS
- MAX_UPLOAD_BYTES: max upload size in bytes, default 10485760

## Run Backend

From repo root, package scripts in [package.json](package.json):

- backend:dev starts FastAPI with reload on port 8000
- backend:start starts FastAPI without reload on port 8000

Run with npm scripts:

```bash
npm run backend:dev
```

Or run directly:

```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

## Authentication Model

Protected endpoints require:

- Authorization: Bearer <jwt_token>

JWT claims read by backend:

- sub or user_id: required
- email: optional
- is_premium: optional boolean

Premium-only route also verifies user premium state in Mongo users collection.

## API Endpoints (Current)

Base URL: http://localhost:8000

- GET /health
	- Public health endpoint

- POST /api/v1/ocr/analyze
	- Protected
	- multipart/form-data with file image
	- Returns document_id, image_hash, OCR result

- GET /api/v1/ocr/documents/{document_id}
	- Protected
	- Returns stored OCR document for current user

- GET /api/v1/templates/library
	- Protected and premium-only
	- Returns public templates

- POST /api/v1/templates/save
	- Protected
	- Saves user template

Detailed request and response examples are in [backend/API_OPENAPI_SUMMARY.md](backend/API_OPENAPI_SUMMARY.md).

## Standard Error Response

All handled errors follow this format:

```json
{
	"success": false,
	"error": {
		"code": "string_code",
		"message": "human readable message",
		"details": null
	}
}
```

## Notes For Frontend Integration

- OCR geometry and template coordinates are percentage-based
- Reuse returned document_id from OCR analyze to fetch OCR document later
- Send Bearer token for all protected routes
- Ensure extension origin is allow-listed via ALLOWED_EXTENSION_IDS
