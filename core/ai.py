"""Calling an AI model: one piece of calling code per provider (docs/design.md, "Runs").

Both providers built so far speak OpenAI's Responses API through the official `openai` package:
- `foundry_openai`: OpenAI models deployed in Microsoft Foundry, the production target;
- `openai`: the OpenAI API itself, for testing while there is no Foundry endpoint (Nov 28, Maaz).
They differ only in the address and key, which the app passes in (`core/` never reads settings): `credentials` maps a
provider code to {"base_url": ..., "api_key": ...}.

The answer shape goes to the model as a strict JSON schema, so it cannot add or leave out a field. Answers are
streamed with a generous output limit. There are no retries, not even the SDK's own.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from openai import OpenAI

MAX_OUTPUT_TOKENS = 64000
PROVIDERS = ("foundry_openai", "openai")  # the providers this code can call, production first


@dataclass
class Model:
    """A model as a Run uses it: from reference.agent_model and its provider."""

    agent_model_id: int
    agent_provider_code: str
    agent_model_name: str
    input_usd_per_million: float | None
    cached_input_usd_per_million: float | None
    output_usd_per_million: float | None


@dataclass
class Usage:
    started_time: datetime
    completed_time: datetime
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    cost_usd: float | None = None


class AIError(Exception):
    """A model call that failed or gave no usable answer. The message says why, for the Run log."""


def client(credentials, model):
    found = credentials.get(model.agent_provider_code)
    if not found or not found.get("api_key"):
        raise AIError(f"No key is set for provider {model.agent_provider_code}.")
    return OpenAI(api_key=found["api_key"], base_url=found.get("base_url") or None, max_retries=0, timeout=900)


def call(ai_client, model, effort, input_items, schema=None, tools=None, previous_response_id=None):
    """One model call. Returns (response, usage). `schema` is the answer's strict JSON schema ({"name", "schema"});
    `tools` are function tools for a tool based Run."""
    kwargs = {"model": model.agent_model_name, "input": input_items, "max_output_tokens": MAX_OUTPUT_TOKENS}
    if effort and effort != "default":
        kwargs["reasoning"] = {"effort": effort}
    if schema:
        kwargs["text"] = {"format": {"type": "json_schema", "strict": True, **schema}}
    if tools:
        kwargs["tools"] = tools
        kwargs["parallel_tool_calls"] = True
    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id
    started = datetime.now(timezone.utc)
    try:
        with ai_client.responses.stream(**kwargs) as stream:
            response = stream.get_final_response()
    except Exception as error:  # the SDK's own errors: network, refused key, unknown model, bad request
        raise AIError(f"The model call failed: {error}") from error
    return response, usage(model, response, started)


def usage(model, response, started):
    used = Usage(started_time=started, completed_time=datetime.now(timezone.utc))
    u = getattr(response, "usage", None)
    if u is not None:
        used.input_tokens = u.input_tokens or 0
        used.cached_input_tokens = getattr(u.input_tokens_details, "cached_tokens", 0) or 0
        used.output_tokens = u.output_tokens or 0
        used.reasoning_output_tokens = getattr(u.output_tokens_details, "reasoning_tokens", 0) or 0
    prices = (model.input_usd_per_million, model.cached_input_usd_per_million, model.output_usd_per_million)
    if None not in prices:
        fresh = used.input_tokens - used.cached_input_tokens
        used.cost_usd = round((fresh * float(prices[0]) + used.cached_input_tokens * float(prices[1])
                               + used.output_tokens * float(prices[2])) / 1_000_000, 6)
    return used


def answer_json(response):
    """The answer of a one shot call as a dict. Cut off or refused answers raise AIError (RUN-006)."""
    if response.status != "completed":
        reason = getattr(response.incomplete_details, "reason", None) or response.status
        raise AIError(f"The answer was cut off ({reason}).")
    for item in response.output:
        for part in getattr(item, "content", None) or []:
            if part.type == "refusal":
                raise AIError(f"The model refused: {part.refusal}")
    try:
        return json.loads(response.output_text)
    except (ValueError, TypeError) as error:
        raise AIError("The answer is not the JSON the step asked for.") from error
