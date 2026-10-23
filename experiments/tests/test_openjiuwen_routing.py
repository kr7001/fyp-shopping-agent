"""OpenRouter provider routing through openJiuwen's own client (23 October 2026): the body the
OpenAI SDK builds carries "provider" for the routed model, none for another, and with routing
off is byte for byte the body without the wrapper. Its HTTP sending is stubbed, so nothing
leaves the machine.

It imports nothing of the repository but `provider_routing`, so it runs under agent-core's
interpreter, which has openJiuwen, as well as under the one `make test` uses, where it is
skipped when openJiuwen cannot be imported, as in a checkout without agent-core:

    cd experiments/tests && PYTHONDONTWRITEBYTECODE=1 ../../agent/agent-core/.venv/bin/python \
        -m unittest test_openjiuwen_routing -v
"""
import asyncio
import json
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "runners"))
import provider_routing  # noqa: E402

DEEPSEEK, HAIKU = "deepseek/deepseek-v4-flash", "anthropic/claude-haiku-4.5"
ROUTE = provider_routing.PROPOSED[DEEPSEEK]
ON = {provider_routing.ENV: json.dumps(provider_routing.PROPOSED)}


class ThroughOpenJiuwen(unittest.TestCase):
    """openJiuwen's own client, its HTTP sending stubbed so nothing leaves the machine: the
    body the OpenAI SDK builds carries "provider" for the routed model, none for another,
    and with routing off is byte for byte the body without the wrapper."""

    def setUp(self):
        try:
            import httpx  # noqa: F401
            from openjiuwen.core.foundation.llm.model_clients import create_model_client  # noqa: F401
            from openjiuwen.core.foundation.llm.model_clients.openai_model_client import OpenAIModelClient
        except ImportError as missing:
            self.skipTest(f"openJiuwen cannot be imported here: {missing}")
        self.client_class = OpenAIModelClient
        original = OpenAIModelClient._build_request_params
        self.addCleanup(setattr, OpenAIModelClient, "_build_request_params", original)

    def body(self, model: str) -> dict:
        import httpx
        from openjiuwen.core.foundation.llm.model_clients import create_model_client
        from openjiuwen.core.foundation.llm.schema.config import ModelClientConfig, ModelRequestConfig
        sent = []

        async def send(client, request, **kwargs):
            sent.append(json.loads(request.content))
            return httpx.Response(200, request=request, json={
                "id": "gen-test", "object": "chat.completion", "created": 0, "model": model,
                "provider": "GMICloud",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6}})

        client = create_model_client(
            ModelClientConfig(client_provider="OpenRouter", api_key="sk-not-a-key",
                              api_base="https://openrouter.ai/api/v1"),
            ModelRequestConfig(model=model, temperature=0.2, top_p=0.1))
        with mock.patch.object(httpx.AsyncClient, "send", send):
            asyncio.run(client.invoke(messages=[{"role": "user", "content": "hi"}]))
        return sent[-1]

    def test_the_body_sent(self):
        bare = {model: self.body(model) for model in (DEEPSEEK, HAIKU)}
        provider_routing.apply_to_agent(self.client_class, {})
        self.assertEqual({model: self.body(model) for model in (DEEPSEEK, HAIKU)}, bare)
        provider_routing.apply_to_agent(self.client_class, ON)
        routed = {model: self.body(model) for model in (DEEPSEEK, HAIKU)}
        self.assertEqual(routed[DEEPSEEK], {**bare[DEEPSEEK], "provider": ROUTE})
        self.assertEqual(routed[HAIKU], bare[HAIKU])


if __name__ == "__main__":
    unittest.main()
