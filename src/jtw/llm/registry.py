"""Builds providers from a project's configuration and routes calls to them.

This is the only place model IDs meet providers: an MT column id, ``draft`` or ``deep_dive``
resolves to a :class:`Route` (provider, model, label). Every call through a route is checked
against the model it asked for, so nothing silently substitutes a model.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from jtw.config import ModelRef, ProjectConfig
from jtw.llm.base import Message, ModelMismatch, ModelResult, Provider

#: Builds a provider by name (``"anthropic"`` / ``"openai"``) for a given project.
ProviderFactory = Callable[[str, ProjectConfig], Provider]

# Dated snapshot suffixes: "-20260101" (Anthropic) or "-2026-01-01" (OpenAI).
_SNAPSHOT_SUFFIX_RE = re.compile(r"^-(\d{8}|\d{4}-\d{2}-\d{2})$")


def model_matches(returned: str, requested: str) -> bool:
    """True if ``returned`` is ``requested`` or a dated snapshot of it."""
    if returned == requested:
        return True
    if not returned.startswith(requested):
        return False
    return _SNAPSHOT_SUFFIX_RE.match(returned[len(requested) :]) is not None


def check_model(result: ModelResult, requested: str) -> ModelResult:
    if not model_matches(result.model, requested):
        raise ModelMismatch(requested, result.model)
    return result


def default_factory(name: str, config: ProjectConfig) -> Provider:
    timeout = config.limits.request_timeout_s
    if name == "anthropic":
        from jtw.llm.anthropic import AnthropicProvider

        return AnthropicProvider(timeout_s=timeout)
    if name == "openai":
        from jtw.llm.openai import OpenAIProvider

        return OpenAIProvider(timeout_s=timeout)
    raise ValueError(f"unknown provider {name!r}")


@dataclass(frozen=True)
class Route:
    """A provider bound to one model."""

    provider: Provider
    model: str
    label: str

    def complete(self, prompt: str, *, system: str | None = None, max_tokens: int) -> ModelResult:
        result = self.provider.complete(
            prompt, model=self.model, system=system, max_tokens=max_tokens
        )
        return check_model(result, self.model)

    def conversation(
        self, messages: Sequence[Message], *, system: str | None = None, max_tokens: int
    ) -> ModelResult:
        result = self.provider.conversation(
            messages, model=self.model, system=system, max_tokens=max_tokens
        )
        return check_model(result, self.model)


class Registry:
    """Routes for one project. Providers are built lazily and shared between routes."""

    def __init__(self, config: ProjectConfig, factory: ProviderFactory = default_factory) -> None:
        self._config = config
        self._factory = factory
        self._providers: dict[str, Provider] = {}

    def provider(self, name: str) -> Provider:
        if name not in self._providers:
            self._providers[name] = self._factory(name, self._config)
        return self._providers[name]

    def column(self, column_id: str) -> Route:
        try:
            spec = self._config.mt.column[column_id]
        except KeyError:
            raise KeyError(f"no MT column {column_id!r} in this project") from None
        return Route(self.provider(spec.provider), spec.model, spec.label)

    def columns(self) -> dict[str, Route]:
        return {column_id: self.column(column_id) for column_id in self._config.columns}

    def draft(self) -> Route:
        return self._route(self._config.synthesis.draft, "Draft")

    def deep_dive(self) -> Route:
        return self._route(self._config.synthesis.deep_dive, "Deep Dive")

    def _route(self, ref: ModelRef, label: str) -> Route:
        return Route(self.provider(ref.provider), ref.model, label)


def build_registry(config: ProjectConfig, factory: ProviderFactory = default_factory) -> Registry:
    return Registry(config, factory)
