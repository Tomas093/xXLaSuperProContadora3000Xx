from __future__ import annotations

import os
from abc import ABC, abstractmethod

from .errors import AIProviderError
from .providers import AIProvider, AnthropicProvider, GeminiProvider, OpenAIProvider, ProviderModelOptions


class ProviderResolver(ABC):
    @abstractmethod
    def matches(self, provider: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def matches_model(self, model: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def create(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        api_url: str | None = None,
    ) -> AIProvider:
        raise NotImplementedError

    @abstractmethod
    def supported_names(self) -> tuple[str, ...]:
        raise NotImplementedError

    def _first_env(self, names: tuple[str, ...]) -> str | None:
        for name in names:
            value = os.getenv(name)
            if value:
                return value
        return None

    def _api_key_from_env(self, names: tuple[str, ...], provider_name: str) -> str:
        resolved_key = self._first_env(names)
        if resolved_key:
            return resolved_key

        env_names = ", ".join(names)
        raise AIProviderError(f"No API key was provided for provider '{provider_name}'. Set one of: {env_names}.")

    def _validate_model(self, *, provider_name: str, model: str, accepted_models: tuple[str, ...]) -> None:
        if self.matches_model(model):
            return

        raise AIProviderError(
            f"Model '{model}' does not match provider '{provider_name}'. "
            f"Accepted models for {provider_name}: {', '.join(accepted_models)}."
        )


class AnthropicProviderResolver(ProviderResolver):
    PROVIDER_NAMES = ("anthropic", "claude")
    API_KEY_ENV_NAMES = ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY")
    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    ACCEPTED_MODELS = (
        "claude-opus-4-1-20250805",
        "claude-opus-4-20250514",
        "claude-opus-4-0",
        "claude-sonnet-4-20250514",
        "claude-sonnet-4-0",
        "claude-sonnet-4-6",
        "claude-3-7-sonnet-20250219",
        "claude-3-7-sonnet-latest",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-20241022",
        "claude-3-5-haiku-latest",
        "claude-3-haiku-20240307",
    )

    def matches(self, provider: str) -> bool:
        return normalize_provider_token(provider) in self.PROVIDER_NAMES

    def matches_model(self, model: str) -> bool:
        return normalize_model_name(model) in {normalize_model_name(accepted_model) for accepted_model in self.ACCEPTED_MODELS}

    def create(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        api_url: str | None = None,
    ) -> AIProvider:
        resolved_key = api_key or self._api_key_from_env(self.API_KEY_ENV_NAMES, "anthropic")
        resolved_model = model or self.DEFAULT_MODEL
        self._validate_model(provider_name="anthropic", model=resolved_model, accepted_models=self.ACCEPTED_MODELS)
        return AnthropicProvider(api_key=resolved_key, model=resolved_model, api_url=api_url)

    def supported_names(self) -> tuple[str, ...]:
        return self.PROVIDER_NAMES


class OpenAIProviderResolver(ProviderResolver):
    PROVIDER_NAMES = ("openai", "chatgpt")
    API_KEY_ENV_NAMES = ("OPENAI_API_KEY", "OPEN_AI_API_KEY")
    DEFAULT_MODEL = "gpt-5.4-mini"
    MODEL_OPTIONS = {
        "gpt-5.5-pro": ProviderModelOptions(token_limit_parameter="max_completion_tokens", supports_temperature=False),
        "gpt-5.5": ProviderModelOptions(token_limit_parameter="max_completion_tokens", supports_temperature=False),
        "gpt-5.4-pro": ProviderModelOptions(token_limit_parameter="max_completion_tokens", supports_temperature=False),
        "gpt-5.4": ProviderModelOptions(token_limit_parameter="max_completion_tokens", supports_temperature=False),
        "gpt-5.4-mini": ProviderModelOptions(token_limit_parameter="max_completion_tokens", supports_temperature=False),
    }
    ACCEPTED_MODELS = (
        "gpt-5.5-pro",
        "gpt-5.5",
        "gpt-5.4-pro",
        "gpt-5.4",
        "gpt-5.4-mini",
    )

    def matches(self, provider: str) -> bool:
        return normalize_provider_token(provider) in self.PROVIDER_NAMES

    def matches_model(self, model: str) -> bool:
        return normalize_model_name(model) in {normalize_model_name(accepted_model) for accepted_model in self.ACCEPTED_MODELS}

    def create(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        api_url: str | None = None,
    ) -> AIProvider:
        resolved_key = api_key or self._api_key_from_env(self.API_KEY_ENV_NAMES, "openai")
        resolved_model = model or self.DEFAULT_MODEL
        self._validate_model(provider_name="openai", model=resolved_model, accepted_models=self.ACCEPTED_MODELS)
        model_options = self.MODEL_OPTIONS[normalize_model_name(resolved_model)]
        return OpenAIProvider(api_key=resolved_key, model=resolved_model, api_url=api_url, model_options=model_options)

    def supported_names(self) -> tuple[str, ...]:
        return self.PROVIDER_NAMES


class GeminiProviderResolver(ProviderResolver):
    PROVIDER_NAMES = ("gemini", "google", "google-gemini")
    API_KEY_ENV_NAMES = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
    DEFAULT_MODEL = "gemini-2.5-pro"
    ACCEPTED_MODELS = (
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro-preview-customtools",
        "gemini-3-pro-preview",
        "gemini-3.0-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    )

    def matches(self, provider: str) -> bool:
        return normalize_provider_token(provider) in self.PROVIDER_NAMES

    def matches_model(self, model: str) -> bool:
        return normalize_model_name(model) in {normalize_model_name(accepted_model) for accepted_model in self.ACCEPTED_MODELS}

    def create(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        api_url: str | None = None,
    ) -> AIProvider:
        resolved_key = api_key or self._api_key_from_env(self.API_KEY_ENV_NAMES, "gemini")
        resolved_model = model or self.DEFAULT_MODEL
        self._validate_model(provider_name="gemini", model=resolved_model, accepted_models=self.ACCEPTED_MODELS)
        return GeminiProvider(api_key=resolved_key, model=resolved_model, api_url=api_url)

    def supported_names(self) -> tuple[str, ...]:
        return self.PROVIDER_NAMES


PROVIDER_RESOLVERS: tuple[ProviderResolver, ...] = (
    AnthropicProviderResolver(),
    OpenAIProviderResolver(),
    GeminiProviderResolver(),
)


def normalize_provider_token(provider: str) -> str:
    return provider.strip().lower().replace("_", "-")


def normalize_model_name(model: str) -> str:
    return model.strip().lower()


def find_provider_resolver(provider: str) -> ProviderResolver:
    for resolver in PROVIDER_RESOLVERS:
        if resolver.matches(provider):
            return resolver

    supported = ", ".join(resolver.supported_names()[0] for resolver in PROVIDER_RESOLVERS)
    raise AIProviderError(f"Unsupported AI provider '{provider}'. Supported providers: {supported}.")


def supported_provider_choices() -> list[str]:
    choices: list[str] = []
    for resolver in PROVIDER_RESOLVERS:
        choices.extend(resolver.supported_names())
    return choices
