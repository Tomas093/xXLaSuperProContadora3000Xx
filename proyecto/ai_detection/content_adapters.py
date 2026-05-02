from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ContentAdapter(ABC):
    @abstractmethod
    def adapt(self, content: list[dict[str, Any]]) -> Any:
        raise NotImplementedError


class AnthropicContentAdapter(ContentAdapter):
    def adapt(self, content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for block in content:
            if block.get("type") == "text":
                text_block: dict[str, Any] = {"type": "text", "text": str(block.get("text", ""))}
                if "cache_control" in block:
                    text_block["cache_control"] = block["cache_control"]
                converted.append(text_block)
            elif block.get("type") == "image":
                converted.append(block)
        return converted


class OpenAIContentAdapter(ContentAdapter):
    def adapt(self, content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for block in content:
            if block.get("type") == "text":
                converted.append({"type": "text", "text": str(block.get("text", ""))})
            elif block.get("type") == "image_url":
                converted.append(block)
        return converted


class GeminiContentAdapter(ContentAdapter):
    def adapt(self, content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for block in content:
            if block.get("type") == "text":
                converted.append({"text": str(block.get("text", ""))})
            elif "inline_data" in block:
                converted.append(block)
        return converted
