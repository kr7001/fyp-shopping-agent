"""OpenRouter provider routing, off unless IGR_PROVIDER_ROUTING is set (23 October 2026,
from the pilot: its DeepSeek calls were charged 2.16 times list price, 750 of 1,502
served by Relace at fp4, whose cached input costs what uncached does, and 195 by Parasail).

The variable holds JSON that maps a model id to OpenRouter's request-body "provider" object.
It applies to every call to that model and to no other, so one setting serves a chain that
runs two models, and every arm of a model gets the same routing:

    IGR_PROVIDER_ROUTING='{"deepseek/deepseek-v4-flash": {"order": ["gmicloud", "deepinfra",
        "streamlake"], "allow_fallbacks": false}}'

The slugs are those of GET https://openrouter.ai/api/v1/providers (gmicloud, deepinfra,
streamlake, read on 23 October 2026), never display names. Three readers take it alike: the
agent's runner, which routes openJiuwen's requests for the run (`apply_to_agent`); the parse
call (`parse_probe.call_model`); and the suite, which records it in every payload. Stdlib
only, since the runner imports it under agent-core's interpreter.
"""

from __future__ import annotations

import json
import os

ENV = "IGR_PROVIDER_ROUTING"
# The attribute that marks the wrapper `apply_to_agent` installs, so it is installed once.
MARK = "_igr_provider_routing"
# The value proposed for the protocol, not applied unless IGR_PROVIDER_ROUTING is set to it:
# DeepSeek V4 Flash at the three fp8 endpoints whose cached input is a fifth of uncached, in
# order, and nowhere else. The slugs were read from GET /api/v1/providers, with no key, on
# 23 October 2026, and each names an endpoint of the model in its endpoint list that day:
# gmicloud GMICloud ($0.091 in, $0.0182 cached), deepinfra DeepInfra ($0.090, $0.018),
# streamlake StreamLake ($0.070, $0.014), per million tokens. "quantizations": ["fp8"] since the
# verifier's check of 281c7e8, so an endpoint that changes its quantisation is not used either
# (part of decision 9).
PROPOSED = {"deepseek/deepseek-v4-flash": {"order": ["gmicloud", "deepinfra", "streamlake"],
                                           "allow_fallbacks": False, "quantizations": ["fp8"]}}
# The fields of OpenRouter's request-body "provider" object as its documentation names them,
# the verifier's list on 23 October 2026. A key outside them, a typo such as "allow_fallback",
# would be sent, and OpenRouter would ignore it without a word, so it is refused.
PROVIDER_KEYS = ("order", "allow_fallbacks", "only", "ignore", "quantizations", "sort",
                 "require_parameters", "data_collection", "max_price")


def unknown_keys(provider: dict) -> list[str]:
    """The keys of a provider object OpenRouter does not document (`PROVIDER_KEYS`), sorted.
    claim.py holds a protocol file's routing to the same list."""
    return sorted(set(provider) - set(PROVIDER_KEYS))


def setting(environ=None) -> dict[str, dict]:
    """The routing by model id, {} when the variable is unset or blank. Anything but a JSON
    object of model ids to objects is refused, so a mistyped setting stops a batch before
    anything is spent rather than quietly routing nothing; since the verifier's check of
    281c7e8 so is an object with a key OpenRouter does not document (`unknown_keys`)."""
    raw = ((os.environ if environ is None else environ).get(ENV) or "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as fault:
        raise ValueError(f"{ENV} is not JSON: {fault}") from None
    if not isinstance(value, dict) or not all(isinstance(model, str) and isinstance(provider, dict)
                                              for model, provider in value.items()):
        raise ValueError(f"{ENV} must map model ids to OpenRouter provider objects, got {raw[:120]!r}")
    for model, provider in value.items():
        if unknown_keys(provider):
            raise ValueError(f"{ENV} gives {model} the provider keys {unknown_keys(provider)}, which OpenRouter "
                             f"does not document ({', '.join(PROVIDER_KEYS)}); it would ignore them without a word")
    return value


def routing_for(model: str | None, environ=None) -> dict | None:
    """The provider object for this model, or None when the model is not routed."""
    return setting(environ).get(model or "")


def apply_to_agent(client_class=None, environ=None) -> dict[str, dict]:
    """Route every request openJiuwen's OpenAI-compatible client builds, the browser
    worker's and the dialogue compressor's alike: the model's provider object is added to
    the request's extra_body, which the OpenAI SDK merges into the JSON body it sends.
    Checked offline on 23 October 2026 against agent-core 18d45d6 with its local patch: the
    body sent for deepseek/deepseek-v4-flash carried "provider", and one for
    anthropic/claude-haiku-4.5 did not. Installed only when the setting routes some model;
    returns the setting. `client_class` is for a test."""
    routing = setting(environ)
    if not routing:
        return {}
    if client_class is None:
        from openjiuwen.core.foundation.llm.model_clients.openai_model_client import OpenAIModelClient
        client_class = OpenAIModelClient
    original = client_class._build_request_params
    # Installed once a process: a second call would wrap the wrapper.
    if getattr(original, MARK, None) is not None:
        return routing

    def with_routing(self, **kwargs):
        params = original(self, **kwargs)
        provider = routing.get(params.get("model"))
        if provider is not None:
            params["extra_body"] = {**(params.get("extra_body") or {}), "provider": provider}
        return params

    setattr(with_routing, MARK, routing)
    client_class._build_request_params = with_routing
    return routing
