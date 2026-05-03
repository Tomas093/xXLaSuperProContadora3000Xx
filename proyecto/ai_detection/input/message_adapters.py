from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MessageAdapter(ABC):
    @abstractmethod
    def build_payload(
        self,
        *,
        model: str,
        system_prompt: str | list[dict[str, Any]],
        provider_content: Any,
        max_tokens: int,
        temperature: float,
        cache_control: dict[str, Any] | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _prompt_to_text(prompt: str | list[dict[str, Any]]) -> str:
        if isinstance(prompt, str):
            return prompt

        parts = []
        for item in prompt:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n\n".join(parts)


class AnthropicMessageAdapter(MessageAdapter):
    def build_payload(
        self,
        *,
        model: str,
        system_prompt: str | list[dict[str, Any]],
        provider_content: Any,
        max_tokens: int,
        temperature: float,
        cache_control: dict[str, Any] | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del provider_options
        payload = {
            "model": model,
            "system": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": provider_content}],
        }
        if cache_control:
            payload["cache_control"] = cache_control
        return payload


class OpenAIMessageAdapter(MessageAdapter):
    def build_payload(
        self,
        *,
        model: str,
        system_prompt: str | list[dict[str, Any]],
        provider_content: Any,
        max_tokens: int,
        temperature: float,
        cache_control: dict[str, Any] | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del cache_control
        provider_options = provider_options or {}
        token_limit_key = str(provider_options.get("token_limit_parameter", "max_tokens"))
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self._prompt_to_text(system_prompt)},
                {"role": "user", "content": provider_content},
            ],
        }
        if provider_options.get("supports_temperature", True):
            payload["temperature"] = temperature
        payload[token_limit_key] = max_tokens
        return payload


class GeminiMessageAdapter(MessageAdapter):
    def build_payload(
        self,
        *,
        model: str,
        system_prompt: str | list[dict[str, Any]],
        provider_content: Any,
        max_tokens: int,
        temperature: float,
        cache_control: dict[str, Any] | None = None,
        provider_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del cache_control, provider_options
        return {
            "system_instruction": {"parts": [{"text": self._prompt_to_text(system_prompt)}]},
            "contents": [
                {
                    "role": "user",
                    "parts": provider_content,
                }
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
