"""What a provider has to send back before the answer counts as a tool call."""

import asyncio
import json

import httpx
import pytest

from tglinks import categorize, llm, triage


@pytest.fixture
def serve(monkeypatch):
    """Point httpx at canned answers instead of the providers."""
    def install(handler):
        original = httpx.AsyncClient

        class Client(original):
            def __init__(self, **kw):
                kw.pop("timeout", None)
                super().__init__(transport=httpx.MockTransport(handler), **kw)

        monkeypatch.setattr(httpx, "AsyncClient", Client)
    return install


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("CEREBRAS_API_KEY", "k")


def tool_call(name: str, arguments) -> dict:
    """An openai-dialect envelope carrying whatever arguments are given."""
    return {"choices": [{"message": {"tool_calls": [
        {"function": {"name": name, "arguments": arguments}},
    ]}}]}


def by_host(answers: dict):
    """A different canned answer per provider, so falling through is visible."""
    def handler(request: httpx.Request) -> httpx.Response:
        for host, body in answers.items():
            if host in request.url.host:
                return httpx.Response(200, json=body)
        raise AssertionError(f"unexpected call to {request.url}")
    return handler


def ask(steps: str, tool: llm.Tool) -> tuple[dict, llm.Step]:
    return asyncio.run(llm.call(llm.chain(steps), "system", "user", tool))


CHAIN = "groq/a,cerebras/b"


def test_a_string_where_the_tool_wants_a_boolean_is_not_a_verdict(serve):
    """bool("false") is True, so a coerced keep would publish a private link."""
    serve(by_host({
        "groq": tool_call("verdict", json.dumps({"keep": "false", "reason": "private"})),
        "cerebras": tool_call("verdict", json.dumps({"keep": False, "reason": "private"})),
    }))
    data, step = ask(CHAIN, triage.TOOL)
    assert step.provider == "cerebras"
    assert data["keep"] is False


def test_an_empty_object_is_not_a_classification(serve):
    serve(by_host({
        "groq": tool_call("classify", "{}"),
        "cerebras": tool_call("classify", json.dumps({
            "category": "place", "tags": [], "title": "MACRO",
            "description": "A museum.", "keywords": [], "confidence": "high",
        })),
    }))
    data, step = ask(CHAIN, categorize.TOOL)
    assert step.provider == "cerebras"
    assert data["title"] == "MACRO"


def test_keywords_as_one_string_still_count_as_an_answer(serve):
    """R5: the array tolerance survives the type check, coercion happens later."""
    serve(by_host({"groq": tool_call("classify", json.dumps({
        "category": "place", "tags": "museum, rome", "title": "MACRO",
        "description": "A museum.", "keywords": "rome, art", "confidence": "high",
    }))}))
    data, step = ask("groq/a", categorize.TOOL)
    assert step.provider == "groq"
    assert categorize.coerce(data)["keywords"] == ["rome", "art"]


def test_a_title_of_the_wrong_type_moves_the_chain_on(serve):
    good = {
        "category": "place", "tags": [], "title": "MACRO",
        "description": "A museum.", "keywords": [], "confidence": "high",
    }
    serve(by_host({
        "groq": tool_call("classify", json.dumps({**good, "title": 7})),
        "cerebras": tool_call("classify", json.dumps(good)),
    }))
    _, step = ask(CHAIN, categorize.TOOL)
    assert step.provider == "cerebras"


def test_a_null_function_falls_through_instead_of_raising(serve):
    serve(by_host({
        "groq": {"choices": [{"message": {"tool_calls": [{"function": None}]}}]},
        "cerebras": tool_call("verdict", json.dumps({"keep": True, "reason": "a jacket"})),
    }))
    data, step = ask(CHAIN, triage.TOOL)
    assert step.provider == "cerebras"
    assert data["keep"] is True


def test_arguments_sent_as_an_object_fall_through_instead_of_raising(serve):
    serve(by_host({
        "groq": tool_call("verdict", {"keep": True, "reason": "a jacket"}),
        "cerebras": tool_call("verdict", json.dumps({"keep": True, "reason": "a jacket"})),
    }))
    _, step = ask(CHAIN, triage.TOOL)
    assert step.provider == "cerebras"


def test_content_null_from_anthropic_is_a_fall_through():
    with pytest.raises(llm.Unavailable):
        llm.anthropic_input({"content": None}, "verdict")


def test_a_whole_chain_of_bad_shapes_leaves_nothing(serve):
    serve(by_host({
        "groq": tool_call("verdict", json.dumps({"reason": "no idea"})),
        "cerebras": tool_call("verdict", json.dumps({"keep": 1, "reason": "no idea"})),
    }))
    with pytest.raises(llm.Unavailable):
        ask(CHAIN, triage.TOOL)


def test_the_gate_drops_a_verdict_that_is_not_a_boolean(monkeypatch):
    """Belt and braces: the one place a truthy string would be published."""
    async def answer(steps, system, user, tool, **kwargs):
        return {"keep": "false", "reason": "private"}, steps[0]

    monkeypatch.setattr(llm, "call", answer)
    kept, why = asyncio.run(
        triage.keep("https://shop.com/x", {}, "", llm.chain("groq/a"))
    )
    assert not kept
    assert why == "no verdict"
