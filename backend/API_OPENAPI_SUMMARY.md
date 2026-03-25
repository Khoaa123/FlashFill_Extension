# FlashFill Backend API Summary (OpenAPI-Friendly)

Base URL:
- `http://localhost:8000`

Auth:
- `Authorization: Bearer <JWT_ACCESS_TOKEN>`

Error format (standardized for all endpoints):
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

## 1) Health
### GET /health
Description:
- Service health check.

Sample response (200):
```json
{
  "status": "ok"
}
```

## 2) OCR Analyze
### POST /api/v1/ocr/analyze
Description:
- Upload image, run preprocess + OCR, store OCR document in MongoDB.

Headers:
- `Authorization: Bearer <token>`
- `Content-Type: multipart/form-data`

Body:
- `file`: image file (`image/png`, `image/jpeg`, ...)

Sample response (200):
```json
{
  "document_id": "67e20a4f6df9f8a123456789",
  "image_hash": "2a741939ba62e39a6665a51c61f642e1c7070c76938d2cc443f7f8b3349ee01f",
  "ocr": {
    "image_width": 1200,
    "image_height": 1600,
    "deskew_angle": 0,
    "blocks": [
      {
        "text": "Invoice 001",
        "confidence": 0.99,
        "bounding_poly": [
          { "x_percent": 10, "y_percent": 10 },
          { "x_percent": 20, "y_percent": 10 },
          { "x_percent": 20, "y_percent": 14 },
          { "x_percent": 10, "y_percent": 14 }
        ],
        "bbox": {
          "x_percent": 10,
          "y_percent": 10,
          "w_percent": 10,
          "h_percent": 4
        }
      }
    ]
  }
}
```

Common errors:
- `400 invalid_image`
- `400 empty_upload`
- `413 http_413` (file too large)
- `502 vision_api_error`

## 3) OCR Document By ID
### GET /api/v1/ocr/documents/{document_id}
Description:
- Get stored OCR output by ID for current authenticated user.

Headers:
- `Authorization: Bearer <token>`

Path params:
- `document_id`: Mongo ObjectId string.

Sample response (200):
```json
{
  "document_id": "67e20a4f6df9f8a123456789",
  "owner_id": "u1",
  "image_hash": "2a741939ba62e39a6665a51c61f642e1c7070c76938d2cc443f7f8b3349ee01f",
  "created_at": "2026-03-25T01:33:48.008260Z",
  "ocr": {
    "image_width": 1200,
    "image_height": 1600,
    "deskew_angle": 0,
    "blocks": []
  }
}
```

Common errors:
- `400 invalid_document_id`
- `404 document_not_found`

## 4) Premium Template Library
### GET /api/v1/templates/library
Description:
- Return public invoice templates library (premium users only).

Headers:
- `Authorization: Bearer <token>`

Sample response (200):
```json
[
  {
    "id": "67e20a4f6df9f8a123456700",
    "owner_id": "system",
    "name": "Invoice A",
    "image_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "original_dimension": { "width": 1000, "height": 1400 },
    "fields": [],
    "is_public": true,
    "created_at": "2026-03-25T00:00:00Z",
    "updated_at": "2026-03-25T00:00:00Z"
  }
]
```

Common errors:
- `403 http_403` (non-premium)

## 5) Save User Template
### POST /api/v1/templates/save
Description:
- Save user-adjusted layout from extension.

Headers:
- `Authorization: Bearer <token>`
- `Content-Type: application/json`

Sample request:
```json
{
  "name": "Receipt layout #1",
  "image_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "original_dimension": { "width": 1080, "height": 1920 },
  "fields": [
    {
      "label": "total",
      "x": 10,
      "y": 20,
      "w": 30,
      "h": 5,
      "field_type": "number"
    }
  ],
  "is_public": false
}
```

Sample response (200):
```json
{
  "id": "67e20a4f6df9f8a123456701",
  "owner_id": "u1",
  "name": "Receipt layout #1",
  "image_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "original_dimension": { "width": 1080, "height": 1920 },
  "fields": [
    {
      "label": "total",
      "x": 10,
      "y": 20,
      "w": 30,
      "h": 5,
      "field_type": "number"
    }
  ],
  "is_public": false,
  "created_at": "2026-03-25T01:33:48.008260Z",
  "updated_at": "2026-03-25T01:33:48.008260Z"
}
```

## Notes for Frontend Team
- Coordinates for fields and OCR geometry are percentage-based for responsive rendering.
- Use `document_id` from OCR Analyze to fetch OCR again via `/api/v1/ocr/documents/{document_id}`.
- Include Bearer token for all protected endpoints.
