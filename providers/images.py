"""Shared PNG plumbing for vendor adapters: data URLs, uploads, media types.

Every adapter ships the same scan image in a vendor-shaped envelope; these
helpers keep the base64/MIME literals in one place.
"""

import base64
from typing import Final

PNG_MEDIA_TYPE: Final = "image/png"
PNG_FILENAME: Final = "image.png"
_DATA_URL_PREFIX = f"data:{PNG_MEDIA_TYPE};base64,"


def png_base64(image: bytes) -> str:
    return base64.b64encode(image).decode("utf-8")


def data_url(image: bytes) -> str:
    """The image as a data: URL — the OpenAI-compatible image_url shape."""
    return _DATA_URL_PREFIX + png_base64(image)


def upload_file_tuple(image: bytes) -> tuple[str, bytes, str]:
    """(filename, bytes, media_type) — the multipart upload shape."""
    return (PNG_FILENAME, image, PNG_MEDIA_TYPE)
