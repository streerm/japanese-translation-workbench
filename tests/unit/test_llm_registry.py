import pytest

from jtw.config import ProjectConfig, load_project
from jtw.llm.anthropic import AnthropicProvider
from jtw.llm.base import ModelMismatch, ModelResult, Provider
from jtw.llm.fake import FakeCall, FakeProvider
from jtw.llm.openai import OpenAIProvider
from jtw.llm.registry import (
    build_registry,
    check_model,
    default_factory,
    model_matches,
)
from jtw.paths import ProjectPaths


@pytest.fixture
def config(mini_paths: ProjectPaths) -> ProjectConfig:
    return load_project("mini").config


@pytest.mark.parametrize(
    ("returned", "requested", "ok"),
    [
        ("claude-opus-5", "claude-opus-5", True),
        ("claude-opus-5-20260101", "claude-opus-5", True),
        ("gpt-6-astra-2026-01-01", "gpt-6-astra", True),
        ("claude-opus-5-5", "claude-opus-5", False),
        ("claude-opus-5-5-20260101", "claude-opus-5", False),
        ("claude-fable-5-1", "claude-opus-5", False),
        ("claude-opus-50", "claude-opus-5", False),
        ("claude-opus", "claude-opus-5", False),
    ],
)
def test_model_matches(returned: str, requested: str, ok: bool) -> None:
    assert model_matches(returned, requested) is ok


def test_check_model_raises() -> None:
    with pytest.raises(ModelMismatch) as info:
        check_model(ModelResult("x", "other"), "wanted")
    assert (info.value.requested, info.value.returned) == ("wanted", "other")


def test_registry_builds_routes_from_config(config: ProjectConfig) -> None:
    built: list[str] = []
    fakes: dict[str, FakeProvider] = {}

    def factory(name: str, cfg: ProjectConfig) -> Provider:
        built.append(name)
        return fakes.setdefault(name, FakeProvider(name=name))

    registry = build_registry(config, factory)
    routes = registry.columns()
    assert list(routes) == ["alpha", "beta"]
    assert (routes["alpha"].model, routes["alpha"].label) == ("fake-model-a", "Model A")
    assert routes["beta"].provider is fakes["openai"]
    assert registry.draft().model == "fake-model-draft"
    assert registry.deep_dive().provider is fakes["anthropic"]
    assert sorted(built) == ["anthropic", "openai"]  # built once each
    with pytest.raises(KeyError, match="gamma"):
        registry.column("gamma")


def test_route_calls_and_guards(config: ProjectConfig) -> None:
    fake = FakeProvider(["ok", "chat", "ok"])
    registry = build_registry(config, lambda name, cfg: fake)
    route = registry.column("alpha")
    assert route.complete("p", system="s", max_tokens=3).text == "ok"
    assert fake.calls[0] == FakeCall(
        "complete", "fake-model-a", "s", 3, ({"role": "user", "content": "p"},)
    )
    assert route.conversation([{"role": "user", "content": "q"}], max_tokens=2).text == "chat"
    fake.served_model = "fake-model-z"
    with pytest.raises(ModelMismatch):
        route.complete("p", max_tokens=1)


def test_default_factory(config: ProjectConfig) -> None:
    assert isinstance(default_factory("anthropic", config), AnthropicProvider)
    assert isinstance(default_factory("openai", config), OpenAIProvider)
    with pytest.raises(ValueError):
        default_factory("mystery", config)


def test_fake_provider_script_kinds() -> None:
    error = RuntimeError("boom")
    canned = ModelResult("canned", "m", stop_reason="max_tokens")
    fake = FakeProvider([error, canned, lambda call: call.prompt.upper()])
    with pytest.raises(RuntimeError, match="boom"):
        fake.complete("a", model="m", max_tokens=1)
    assert fake.complete("b", model="m", max_tokens=1) is canned
    assert fake.complete("echo", model="m", max_tokens=1).text == "ECHO"
    with pytest.raises(AssertionError, match="exhausted"):
        fake.complete("c", model="m", max_tokens=1)
    assert len(fake.calls) == 4
