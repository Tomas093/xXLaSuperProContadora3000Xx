from __future__ import annotations

import base64
from abc import ABC, abstractmethod

from ..errors import AIProviderError


class ImageBlockBuilder(ABC):
    mime_type = "image/png"
    default_suffix = ".png"
    _PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    @abstractmethod
    def build(self, *, file_bytes: bytes, filename: str) -> dict:
        raise NotImplementedError

    def _base64_png(self, *, file_bytes: bytes, filename: str) -> str:
        self._validate_png(file_bytes=file_bytes, filename=filename)
        return base64.b64encode(file_bytes).decode("ascii")

    def _validate_png(self, *, file_bytes: bytes, filename: str) -> None:
        if not filename.lower().endswith(self.default_suffix):
            raise AIProviderError(f"Unsupported image file '{filename}'. Only PNG images are accepted.")
        if not file_bytes.startswith(self._PNG_SIGNATURE):
            raise AIProviderError(f"Unsupported image content for '{filename}'. The file must be a valid PNG image.")


class AnthropicImageBlockBuilder(ImageBlockBuilder):
    def build(self, *, file_bytes: bytes, filename: str) -> dict:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": self.mime_type,
                "data": self._base64_png(file_bytes=file_bytes, filename=filename),
            },
        }


class OpenAIImageBlockBuilder(ImageBlockBuilder):
    def build(self, *, file_bytes: bytes, filename: str) -> dict:
        image_data = self._base64_png(file_bytes=file_bytes, filename=filename)
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{self.mime_type};base64,{image_data}",
            },
        }


class GeminiImageBlockBuilder(ImageBlockBuilder):
    def build(self, *, file_bytes: bytes, filename: str) -> dict:
        return {
            "inline_data": {
                "mime_type": self.mime_type,
                "data": self._base64_png(file_bytes=file_bytes, filename=filename),
            }
        }
