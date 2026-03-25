from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import cv2
import numpy as np
from google.cloud import vision
from pydantic import BaseModel, Field


class NormalizedVertex(BaseModel):
    x_percent: float = Field(ge=0.0, le=100.0)
    y_percent: float = Field(ge=0.0, le=100.0)


class NormalizedBBox(BaseModel):
    x_percent: float = Field(ge=0.0, le=100.0)
    y_percent: float = Field(ge=0.0, le=100.0)
    w_percent: float = Field(ge=0.0, le=100.0)
    h_percent: float = Field(ge=0.0, le=100.0)


class OCRTextBlock(BaseModel):
    text: str
    confidence: float | None = None
    bounding_poly: list[NormalizedVertex]
    bbox: NormalizedBBox


class OCRAnalyzeResponse(BaseModel):
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    deskew_angle: float
    blocks: list[OCRTextBlock]


@lru_cache(maxsize=1)
def get_vision_client() -> vision.ImageAnnotatorClient:
    return vision.ImageAnnotatorClient()


def _decode_image(file_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(file_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Cannot decode uploaded image")
    return image


def _estimate_skew_angle(gray_image: np.ndarray) -> float:
    blur = cv2.GaussianBlur(gray_image, (5, 5), 0)
    _, thresh = cv2.threshold(
        blur,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return 0.0

    rect = cv2.minAreaRect(coords.astype(np.float32))
    angle = rect[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if abs(angle) > 45:
        return 0.0
    return float(angle)


def _rotate_image(image: np.ndarray, angle: float) -> tuple[np.ndarray, np.ndarray]:
    if abs(angle) < 0.01:
        matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
        return image, matrix

    height, width = image.shape[:2]
    center = (width / 2.0, height / 2.0)

    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])

    new_width = int((height * sin) + (width * cos))
    new_height = int((height * cos) + (width * sin))

    matrix[0, 2] += (new_width / 2.0) - center[0]
    matrix[1, 2] += (new_height / 2.0) - center[1]

    rotated = cv2.warpAffine(
        image,
        matrix,
        (new_width, new_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated, matrix


def _encode_png(image: np.ndarray) -> bytes:
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise RuntimeError("Cannot encode preprocessed image")
    return encoded.tobytes()


def _extract_block_text(block: Any) -> str:
    words: list[str] = []
    for paragraph in block.paragraphs:
        for word in paragraph.words:
            text = "".join(symbol.text for symbol in word.symbols)
            if text:
                words.append(text)
    return " ".join(words)


def _apply_inverse_affine(matrix: np.ndarray, x: float, y: float) -> tuple[float, float]:
    original_x = matrix[0, 0] * x + matrix[0, 1] * y + matrix[0, 2]
    original_y = matrix[1, 0] * x + matrix[1, 1] * y + matrix[1, 2]
    return original_x, original_y


def _to_percent(value: float, max_value: int) -> float:
    return (max(0.0, min(value, float(max_value))) / float(max_value)) * 100.0


def _build_bbox(points: list[tuple[float, float]], width: int, height: int) -> NormalizedBBox:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]

    min_x = min(xs)
    min_y = min(ys)
    max_x = max(xs)
    max_y = max(ys)

    return NormalizedBBox(
        x_percent=_to_percent(min_x, width),
        y_percent=_to_percent(min_y, height),
        w_percent=_to_percent(max_x - min_x, width),
        h_percent=_to_percent(max_y - min_y, height),
    )


def _run_document_text_detection(content: bytes) -> vision.AnnotateImageResponse:
    client = get_vision_client()
    image = vision.Image(content=content)
    return client.document_text_detection(image=image)


async def analyze_document(file_bytes: bytes) -> OCRAnalyzeResponse:
    original = _decode_image(file_bytes)
    original_height, original_width = original.shape[:2]

    gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)

    deskew_angle = _estimate_skew_angle(denoised)
    deskewed, forward_matrix = _rotate_image(denoised, deskew_angle)
    inverse_matrix = cv2.invertAffineTransform(forward_matrix)

    payload = _encode_png(deskewed)
    vision_response = await asyncio.to_thread(_run_document_text_detection, payload)

    if vision_response.error.message:
        raise RuntimeError(vision_response.error.message)

    blocks: list[OCRTextBlock] = []
    annotation = vision_response.full_text_annotation

    for page in annotation.pages:
        for block in page.blocks:
            raw_vertices = block.bounding_box.vertices
            mapped_points: list[tuple[float, float]] = []
            normalized_vertices: list[NormalizedVertex] = []

            for vertex in raw_vertices:
                x = float(vertex.x or 0)
                y = float(vertex.y or 0)
                original_x, original_y = _apply_inverse_affine(inverse_matrix, x, y)

                clamped_x = max(0.0, min(original_x, float(original_width)))
                clamped_y = max(0.0, min(original_y, float(original_height)))

                mapped_points.append((clamped_x, clamped_y))
                normalized_vertices.append(
                    NormalizedVertex(
                        x_percent=_to_percent(clamped_x, original_width),
                        y_percent=_to_percent(clamped_y, original_height),
                    )
                )

            if not mapped_points:
                continue

            blocks.append(
                OCRTextBlock(
                    text=_extract_block_text(block),
                    confidence=float(block.confidence) if block.confidence else None,
                    bounding_poly=normalized_vertices,
                    bbox=_build_bbox(mapped_points, original_width, original_height),
                )
            )

    return OCRAnalyzeResponse(
        image_width=original_width,
        image_height=original_height,
        deskew_angle=deskew_angle,
        blocks=blocks,
    )
