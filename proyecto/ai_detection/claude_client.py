from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
from dataclasses import dataclass
import tempfile
from typing import Any
from urllib import error, request


class ClaudeAPIError(RuntimeError):
    """Raised when the Claude API request fails."""


@dataclass
class ClaudeVisionClient:
    api_key: str
    model: str = "claude-sonnet-4-6"
    api_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_version: str = "2023-06-01"
    max_image_dimension: int = 2000

    @classmethod
    def from_env(cls, api_key: str | None = None, model: str | None = None) -> "ClaudeVisionClient":
        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        if not resolved_key:
            raise ClaudeAPIError("No Claude API key was provided. Set ANTHROPIC_API_KEY or paste it in the UI.")

        return cls(
            api_key=resolved_key,
            model=model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        )

    def build_image_block(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
        mime_type = mimetypes.guess_type(filename)[0] or "image/png"
        prepared_bytes = self._prepare_image_bytes(
            file_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
        )
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64.b64encode(prepared_bytes).decode("ascii"),
            },
        }

    def _prepare_image_bytes(self, *, file_bytes: bytes, filename: str, mime_type: str) -> bytes:
        dimensions = self._get_image_dimensions_with_sips(file_bytes=file_bytes, filename=filename)
        if not dimensions:
            return file_bytes

        width, height = dimensions
        if max(width, height) <= self.max_image_dimension:
            return file_bytes

        resized = self._resize_image_with_sips(
            file_bytes=file_bytes,
            filename=filename,
            max_dimension=self.max_image_dimension,
        )
        return resized or file_bytes

    @staticmethod
    def _file_suffix_for_name(filename: str) -> str:
        suffix = Path(filename).suffix
        return suffix if suffix else ".png"

    def _get_image_dimensions_with_sips(self, *, file_bytes: bytes, filename: str) -> tuple[int, int] | None:
        sips = shutil.which("sips")
        if not sips:
            return None

        suffix = self._file_suffix_for_name(filename)
        with tempfile.TemporaryDirectory(prefix="claude_img_") as tmpdir:
            image_path = Path(tmpdir) / f"input{suffix}"
            image_path.write_bytes(file_bytes)

            result = subprocess.run(
                [sips, "-g", "pixelWidth", "-g", "pixelHeight", str(image_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return None

            width_match = re.search(r"pixelWidth:\s*(\d+)", result.stdout)
            height_match = re.search(r"pixelHeight:\s*(\d+)", result.stdout)
            if not width_match or not height_match:
                return None

            return int(width_match.group(1)), int(height_match.group(1))

    def _resize_image_with_sips(self, *, file_bytes: bytes, filename: str, max_dimension: int) -> bytes | None:
        sips = shutil.which("sips")
        if not sips:
            return None

        suffix = self._file_suffix_for_name(filename)
        with tempfile.TemporaryDirectory(prefix="claude_img_") as tmpdir:
            input_path = Path(tmpdir) / f"input{suffix}"
            output_path = Path(tmpdir) / f"output{suffix}"
            input_path.write_bytes(file_bytes)

            result = subprocess.run(
                [sips, "-Z", str(max_dimension), str(input_path), "--out", str(output_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not output_path.exists():
                return None

            return output_path.read_bytes()

    def create_message(
        self,
        *,
        system_prompt: str | list[dict[str, Any]],
        user_content: list[dict[str, Any]],
        max_tokens: int = 4000,
        temperature: float = 0.0,
        cache_control: dict[str, Any] | None = None,
        betas: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "system": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": user_content,
                }
            ],
        }
        if cache_control:
            payload["cache_control"] = cache_control

        body = json.dumps(payload).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
        }
        if betas:
            headers["anthropic-beta"] = ",".join(betas)

        req = request.Request(
            self.api_url,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ClaudeAPIError(f"Claude API HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise ClaudeAPIError(f"Could not reach Claude API: {exc.reason}") from exc

    @staticmethod
    def extract_text(response_payload: dict[str, Any]) -> str:
        parts = response_payload.get("content", [])
        return "\n".join(part.get("text", "") for part in parts if part.get("type") == "text").strip()

    @staticmethod
    def extract_usage(response_payload: dict[str, Any]) -> dict[str, Any]:
        usage = response_payload.get("usage", {})
        return usage if isinstance(usage, dict) else {}
