"""File storage service - structured filesystem uploads with validation and compression.

Layout:
    {UPLOAD_DIR}/{YYYY-MM-DD}/{task_id}_{kind}_{uuid}.jpg

Kind is one of: 'before', 'after', 'general'. Images are re-encoded to JPEG
(with a max dimension cap) to strip EXIF and normalise size.
"""
from __future__ import annotations

import io
import logging
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Literal, Optional, Tuple

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps

from ..core.config import settings

logger = logging.getLogger("hobb.storage")

Kind = Literal["before", "after", "general"]


def _today_subdir() -> str:
    return date.today().isoformat()


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _validate_upload(upload: UploadFile, size_bytes: int) -> None:
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit",
        )
    if upload.content_type not in settings.allowed_image_types_list:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported content type '{upload.content_type}'. "
                f"Allowed: {', '.join(settings.allowed_image_types_list)}"
            ),
        )


def _compress_image(raw: bytes) -> Tuple[bytes, str]:
    """Decode, EXIF-rotate, downscale to max dimension, re-encode as JPEG.

    Returns (bytes, extension) tuple.
    """
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        max_dim = settings.IMAGE_MAX_DIMENSION
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=settings.IMAGE_JPEG_QUALITY, optimize=True)
        return out.getvalue(), "jpg"
    except Exception as exc:
        logger.exception("image compression failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image: {exc}",
        )


async def save_upload(
    upload: UploadFile,
    *,
    task_id: Optional[str] = None,
    kind: Kind = "general",
) -> dict:
    """Persist uploaded image to structured storage path and return metadata."""
    raw = await upload.read()
    _validate_upload(upload, len(raw))

    compressed, ext = _compress_image(raw)

    subdir = _today_subdir()
    target_dir = Path(settings.UPLOAD_DIR) / subdir
    _ensure_dir(target_dir)

    prefix = f"{task_id}_{kind}" if task_id else f"general_{kind}"
    filename = f"{prefix}_{uuid.uuid4().hex[:10]}.{ext}"
    target_path = target_dir / filename

    with open(target_path, "wb") as fh:
        fh.write(compressed)

    # URL served by nginx (or FastAPI static mount) at /storage/uploads/...
    url = f"/storage/uploads/{subdir}/{filename}"

    logger.info("uploaded file=%s size=%d kind=%s task=%s", url, len(compressed), kind, task_id)
    return {
        "url": url,
        "filename": filename,
        "size_bytes": len(compressed),
        "content_type": "image/jpeg",
        "path": str(target_path),
    }


def delete_file(url: str) -> bool:
    """Remove a file by its public URL. Safe: only touches paths under UPLOAD_DIR."""
    if not url or not url.startswith("/storage/uploads/"):
        return False
    rel = url.replace("/storage/uploads/", "", 1)
    target = Path(settings.UPLOAD_DIR) / rel
    try:
        target.resolve().relative_to(Path(settings.UPLOAD_DIR).resolve())
    except ValueError:
        logger.warning("refusing to delete path outside upload dir: %s", url)
        return False
    try:
        if target.exists():
            os.remove(target)
            return True
    except OSError as exc:
        logger.warning("failed to delete %s: %s", target, exc)
    return False
