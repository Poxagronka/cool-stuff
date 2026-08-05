"""One call shape over several model providers, cheapest first.

Both places this project needs a model — sorting a new link, turning a question
into search words — want the same thing: a single forced tool call with a
schema, no prose. Groq, Cerebras and Google all speak the OpenAI chat
completions dialect and all have a free daily allowance; Anthropic speaks its
own and costs money. So the work goes to a free provider and falls through to
Anthropic when that one is out of quota, down, or answers with nonsense.

Falling through is deliberate rather than clever: a provider that returns
anything other than a well-formed call to the one tool it was given is treated
as unavailable. Quality is what the fallback protects — better to pay for one
request than to write a bad note that stays in the vault.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass

import httpx

log = logging.getLogger("tglinks")

# every provider here answers a forced tool call; "openai" ones share a dialect
PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", "openai"),
    "cerebras": ("https://api.cerebras.ai/v1/chat/completions", "CEREBRAS_API_KEY", "openai"),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "GEMINI_API_KEY",
        "openai",
    ),
    "anthropic": ("https://api.anthropic.com/v1/messages", "ANTHROPIC_API_KEY", "anthropic"),
}


class Unavailable(Exception):
    """This provider did not deliver; the next one in the chain should try."""


# how many calls each provider has served since this process started, keyed
# "provider/model tool". the point of a chain is that the free providers do the
# work and the paid one is the fallback, and nothing said whether that was
# still true: every answer looks the same from the outside. counted here rather
# than in the callers because every call goes through this module
SERVED: dict[str, int] = {}


@dataclass(frozen=True)
class Step:
    """One provider and the model to ask for, as written in a chain string."""

    provider: str
    model: str

    @property
    def url(self) -> str:
        return PROVIDERS[self.provider][0]

    @property
    def key(self) -> str:
        return os.getenv(PROVIDERS[self.provider][1], "")

    @property
    def dialect(self) -> str:
        return PROVIDERS[self.provider][2]

    def __str__(self) -> str:
        return f"{self.provider}/{self.model}"


def chain(spec: str) -> list[Step]:
    """"groq/llama-3.3-70b-versatile, anthropic/claude-sonnet-5" into steps."""
    steps = []
    for part in spec.split(","):
        provider, _, model = part.strip().partition("/")
        if provider in PROVIDERS and model:
            steps.append(Step(provider, model))
        elif part.strip():
            log.warning("ignoring unknown provider in chain: %s", part.strip())
    return steps


@dataclass(frozen=True)
class Tool:
    """The one tool a call is forced to make, in both dialects."""

    name: str
    description: str
    schema: dict

    def openai(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }

    def anthropic(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
        }


def openai_body(step: Step, system: str, hint: str, user: str, tool: Tool,
                max_tokens: int) -> dict:
    messages = [{"role": "system", "content": system}]
    # the hint is built out of the vault, and the vault is built out of pages
    # and chat messages other people wrote. that makes it untrusted input, and
    # untrusted input in a system message is the model being told to obey it
    if hint:
        messages.append({"role": "user", "content": hint})
    messages.append({"role": "user", "content": user})
    return {
        "model": step.model,
        "max_tokens": max_tokens,
        "messages": messages,
        "tools": [tool.openai()],
        "tool_choice": {"type": "function", "function": {"name": tool.name}},
    }


def anthropic_body(step: Step, system: str, hint: str, user: str, tool: Tool,
                   max_tokens: int) -> dict:
    # the system block is the same on every call, so it is worth caching
    blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    # same reason as above: the hint comes from the vault, so it travels with
    # the question as data rather than sitting in the system block as our word.
    # one turn rather than two, because this api wants the roles to alternate
    said = f"{hint}\n\n{user}" if hint else user
    return {
        "model": step.model,
        "max_tokens": max_tokens,
        "system": blocks,
        "tools": [tool.anthropic()],
        "tool_choice": {"type": "tool", "name": tool.name},
        "messages": [{"role": "user", "content": said}],
    }


def fits(value: object, declared: object) -> bool:
    """Whether one value matches the json-schema type the tool declared."""
    if declared == "array":
        # a model asked for an array will sometimes send "a, b, c" instead, and
        # categorize.listed() makes a list of that. throwing the string away
        # once cost 316 notes their keywords, so it is tolerated here too
        return isinstance(value, list | str)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if declared == "string":
        return isinstance(value, str)
    if declared == "object":
        return isinstance(value, dict)
    # a type this validator does not know is nobody's business to reject
    return True


def checked(data: dict, tool: "Tool") -> dict:
    """The tool input, or Unavailable when it is not the shape that was asked for.

    Deliberately shallow — required keys, and the declared type of each property
    that is present. It is here because a provider answering `{"keep": "false"}`
    is not disagreeing with the gate, it is failing to call the tool: `bool()` of
    that string is True and the private link gets published. An empty object is
    the same failure quietly wearing a note's clothes.
    """
    for key in tool.schema.get("required", []):
        if key not in data:
            raise Unavailable(f"{tool.name} answered without {key}")
    for key, spec in tool.schema.get("properties", {}).items():
        if key in data and not fits(data[key], spec.get("type")):
            raise Unavailable(f"{tool.name}.{key} is not a {spec.get('type')}")
    return data


def openai_input(body: dict, name: str) -> dict:
    if not isinstance(body, dict):
        raise Unavailable("response is not an object")
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as err:
        raise Unavailable(f"no message in response: {err}") from err
    if not isinstance(message, dict):
        raise Unavailable("message is not an object")
    calls = message.get("tool_calls")
    if not isinstance(calls, list):
        raise Unavailable("no tool calls in the message")
    for call in calls:
        if not isinstance(call, dict):
            continue
        fn = call.get("function")
        # a null function, or a name that is not ours, is not the call we forced
        if not isinstance(fn, dict) or fn.get("name") != name:
            continue
        raw = fn.get("arguments")
        if raw is None:
            raw = "{}"
        if not isinstance(raw, str):
            raise Unavailable("tool arguments are not a json string")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as err:
            raise Unavailable(f"tool arguments are not json: {err}") from err
        if isinstance(data, dict):
            return data
    raise Unavailable(f"no call to {name}")


def anthropic_input(body: dict, name: str) -> dict:
    if not isinstance(body, dict):
        raise Unavailable("response is not an object")
    content = body.get("content")
    if not isinstance(content, list):
        raise Unavailable("no content in response")
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use" and block.get("name") == name:
            data = block.get("input")
            if isinstance(data, dict):
                return data
    raise Unavailable(f"no call to {name}")


async def once(client: httpx.AsyncClient, step: Step, system: str, hint: str,
               user: str, tool: Tool, max_tokens: int) -> dict:
    """One provider, one attempt. Raises Unavailable on anything unexpected."""
    if not step.key:
        raise Unavailable("no api key configured")
    if step.dialect == "anthropic":
        body = anthropic_body(step, system, hint, user, tool, max_tokens)
        headers = {
            "x-api-key": step.key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    else:
        body = openai_body(step, system, hint, user, tool, max_tokens)
        headers = {"authorization": f"Bearer {step.key}"}
    try:
        resp = await client.post(step.url, json=body, headers=headers)
    except httpx.HTTPError as err:
        raise Unavailable(f"{type(err).__name__}: {err}") from err
    if resp.status_code != 200:
        raise Unavailable(f"http {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except ValueError as err:
        raise Unavailable(f"response is not json: {err}") from err
    if step.dialect == "anthropic":
        return checked(anthropic_input(data, tool.name), tool)
    return checked(openai_input(data, tool.name), tool)


async def call(steps: list[Step], system: str, user: str, tool: Tool,
               hint: str = "", max_tokens: int = 512, timeout: float = 30,
               retries: int = 1) -> tuple[dict, Step]:
    """The first well-formed tool call the chain produces, and who produced it.

    Retries are per provider and only worth it for work that is not waiting on
    a person: a search box would rather move to the next provider than sit
    through a backoff.
    """
    if not steps:
        raise Unavailable("empty chain")
    trouble = []
    async with httpx.AsyncClient(timeout=timeout) as client:
        for step in steps:
            delay = 1.0
            for attempt in range(retries):
                try:
                    data = await once(client, step, system, hint, user, tool, max_tokens)
                except Unavailable as err:
                    trouble.append(f"{step}: {err}")
                    if attempt + 1 < retries:
                        await asyncio.sleep(delay)
                        delay *= 2
                    continue
                mark = f"{step} {tool.name}"
                SERVED[mark] = SERVED.get(mark, 0) + 1
                # one line per call, so `fly logs | grep 'llm served'` says who
                # is doing the work and how much of it the fallback took
                log.info("llm served: %s, %d since boot", mark, SERVED[mark])
                return data, step
            log.info("provider fell through: %s", trouble[-1])
    raise Unavailable("; ".join(trouble))
