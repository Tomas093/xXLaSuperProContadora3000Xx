from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Protocol
from urllib import error, request

from .content_adapters import (
    AnthropicContentAdapter,
    ContentAdapter,
    GeminiContentAdapter,
    OpenAIContentAdapter,
)
from .errors import AIProviderError
from .input.image_builders import (
    AnthropicImageBlockBuilder,
    GeminiImageBlockBuilder,
    ImageBlockBuilder,
    OpenAIImageBlockBuilder,
)
from .input.message_adapters import (
    AnthropicMessageAdapter,
    GeminiMessageAdapter,
    MessageAdapter,
    OpenAIMessageAdapter,
)


class AIProvider(Protocol):
    provider_name: str
    model: str

    def build_image_block(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
        ...

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
        ...

    def extract_text(self, response_payload: dict[str, Any]) -> str:
        ...

    def extract_usage(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass
class BaseVisionProvider(ABC):
    api_key: str
    model: str
    api_url: str | None = None
    provider_name: str = "base"
    max_image_dimension: int = 2000
    image_builder: ImageBlockBuilder = field(default_factory=AnthropicImageBlockBuilder)
    content_adapter: ContentAdapter = field(default_factory=AnthropicContentAdapter)
    message_adapter: MessageAdapter = field(default_factory=AnthropicMessageAdapter)

    def build_image_block(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
        prepared_bytes = self._prepare_image_bytes(file_bytes=file_bytes, filename=filename)
        return self.image_builder.build(file_bytes=prepared_bytes, filename=filename)

    def _prepare_image_bytes(self, *, file_bytes: bytes, filename: str) -> bytes:
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
        with tempfile.TemporaryDirectory(prefix="ai_img_") as tmpdir:
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
        with tempfile.TemporaryDirectory(prefix="ai_img_") as tmpdir:
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

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def extract_text(self, response_payload: dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    def extract_usage(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], provider_name: str) -> dict[str, Any]:
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json", **headers},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AIProviderError(f"{provider_name} API HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise AIProviderError(f"Could not reach {provider_name} API: {exc.reason}") from exc


@dataclass
class AnthropicProvider(BaseVisionProvider):
    provider_name: str = "anthropic"
    anthropic_version: str = "2023-06-01"
    image_builder: ImageBlockBuilder = field(default_factory=AnthropicImageBlockBuilder)
    content_adapter: ContentAdapter = field(default_factory=AnthropicContentAdapter)
    message_adapter: MessageAdapter = field(default_factory=AnthropicMessageAdapter)

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
        payload = self.message_adapter.build_payload(
            model=self.model,
            system_prompt=system_prompt,
            provider_content=self.content_adapter.adapt(user_content),
            max_tokens=max_tokens,
            temperature=temperature,
            cache_control=cache_control,
        )
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
        }
        if betas:
            headers["anthropic-beta"] = ",".join(betas)

        return self._post_json(
            self.api_url or "https://api.anthropic.com/v1/messages",
            payload,
            headers,
            self.provider_name,
        )

    def extract_text(self, response_payload: dict[str, Any]) -> str:
        parts = response_payload.get("content", [])
        return "\n".join(part.get("text", "") for part in parts if part.get("type") == "text").strip()

    def extract_usage(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        usage = response_payload.get("usage", {})
        return usage if isinstance(usage, dict) else {}


@dataclass
class OpenAIProvider(BaseVisionProvider):
    provider_name: str = "openai"
    image_builder: ImageBlockBuilder = field(default_factory=OpenAIImageBlockBuilder)
    content_adapter: ContentAdapter = field(default_factory=OpenAIContentAdapter)
    message_adapter: MessageAdapter = field(default_factory=OpenAIMessageAdapter)

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
        del cache_control, betas
        payload = self.message_adapter.build_payload(
            model=self.model,
            system_prompt=system_prompt,
            provider_content=self.content_adapter.adapt(user_content),
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return self._post_json(
            self.api_url or "https://api.openai.com/v1/chat/completions",
            payload,
            {"authorization": f"Bearer {self.api_key}"},
            self.provider_name,
        )

    def extract_text(self, response_payload: dict[str, Any]) -> str:
        choices = response_payload.get("choices", [])
        if not choices or not isinstance(choices[0], dict):
            return ""

        message = choices[0].get("message", {})
        content = message.get("content", "") if isinstance(message, dict) else ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "\n".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
        return ""

    def extract_usage(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        usage = response_payload.get("usage", {})
        if not isinstance(usage, dict):
            return {}
        return {
            "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "output_tokens": int(usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
        }


@dataclass
class GeminiProvider(BaseVisionProvider):
    provider_name: str = "gemini"
    image_builder: ImageBlockBuilder = field(default_factory=GeminiImageBlockBuilder)
    content_adapter: ContentAdapter = field(default_factory=GeminiContentAdapter)
    message_adapter: MessageAdapter = field(default_factory=GeminiMessageAdapter)

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
        del cache_control, betas
        payload = self.message_adapter.build_payload(
            model=self.model,
            system_prompt=system_prompt,
            provider_content=self.content_adapter.adapt(user_content),
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return self._post_json(self._resolved_api_url(), payload, {}, self.provider_name)

    def _resolved_api_url(self) -> str:
        base_url = self.api_url or "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        url = base_url.format(model=self.model).rstrip("/")
        separator = "&" if "?" in url else "?"
        if "key=" not in url:
            url = f"{url}{separator}key={self.api_key}"
        return url

    def extract_text(self, response_payload: dict[str, Any]) -> str:
        candidates = response_payload.get("candidates", [])
        if not candidates or not isinstance(candidates[0], dict):
            return ""

        content = candidates[0].get("content", {})
        parts = content.get("parts", []) if isinstance(content, dict) else []
        return "\n".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ).strip()

    def extract_usage(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        usage = response_payload.get("usageMetadata", {})
        if not isinstance(usage, dict):
            return {}
        return {
            "input_tokens": int(usage.get("promptTokenCount", 0) or 0),
            "output_tokens": int(usage.get("candidatesTokenCount", 0) or 0),
            "total_tokens": int(usage.get("totalTokenCount", 0) or 0),
        }
