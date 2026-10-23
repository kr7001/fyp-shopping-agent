"""OpenRouter provider routing (23 October 2026, from the pilot, whose DeepSeek calls were
charged 2.16 times list price): IGR_PROVIDER_ROUTING, a JSON map from a model id to
OpenRouter's request-body "provider" object, off when unset.

What is held here: the setting refuses a malformed value; the agent's requests are routed by
a wrapper of openJiuwen's request builder, for the named model only and with nothing else of
the request changed, installed by the runner and recorded in its run record; the parse call's
body carries the same object and its serving provider is returned and recorded; the suite
records the routing in every payload and the providers per run; under routing a parse call
that fails voids its slot; and the log's providers are counted one per completion. Every rule
fires on a planted fault and stays quiet when off, each fault planted with a fresh bytecode
cache (LESSONS 31, 39). Nothing here calls a model or touches the shop.

openJiuwen's own client, its HTTP sending stubbed, is in test_openjiuwen_routing.py, which
imports nothing else of the repository so that it runs under agent-core's interpreter too.
"""
import asyncio
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

import parse_probe  # noqa: E402
import plan_probe  # noqa: E402
import provider_routing  # noqa: E402
import suite  # noqa: E402
import trace_stats  # noqa: E402
import voids  # noqa: E402
from test_box import thornwood_page  # noqa: E402
from test_claim_arms import run_suite  # noqa: E402
from test_model_parser import keyed_tasks, replying  # noqa: E402

DEEPSEEK, HAIKU = "deepseek/deepseek-v4-flash", "anthropic/claude-haiku-4.5"
ROUTE = provider_routing.PROPOSED[DEEPSEEK]
ON = {provider_routing.ENV: json.dumps(provider_routing.PROPOSED)}
RUNNER = paths.EXPERIMENTS / "runners" / "run_browser_task.py"
PARAPHRASES = paths.TASKS / "paraphrases_v1.json"


def completion(provider: str | None, prompt: int = 100) -> str:
    """One logged completion as openJiuwen's log prints it: the ChatCompletion repr with its
    usage and, unless None, the provider OpenRouter served it from. Made up, no real call's."""
    served = f", provider='{provider}'" if provider is not None else ""
    return (f"2026-10-23 12:00:00 | llm | default_trace_id | INFO | {{\"event_type\": \"llm_call_end\", "
            f"\"metadata\": {{\"response\": \"ChatCompletion(id='gen-1-x', choices=[], created=0, "
            f"model='{DEEPSEEK}', object='chat.completion', usage=CompletionUsage(completion_tokens=10, "
            f"prompt_tokens={prompt}, total_tokens={prompt + 10}, cost=0.0001, is_byok=False){served})\"}}}}\n")


# ---------------------------------------------------------------------------
# The setting

class TheSetting(unittest.TestCase):
    """Planted: a malformed value accepted."""

    def test_off_when_unset_or_blank(self):
        for environ in ({}, {provider_routing.ENV: ""}, {provider_routing.ENV: "  "}):
            self.assertEqual(provider_routing.setting(environ), {})
            self.assertIsNone(provider_routing.routing_for(DEEPSEEK, environ))

    def test_on_it_routes_the_named_model_and_no_other(self):
        self.assertEqual(provider_routing.routing_for(DEEPSEEK, ON), ROUTE)
        self.assertIsNone(provider_routing.routing_for(HAIKU, ON))
        self.assertIsNone(provider_routing.routing_for(None, ON))

    def test_a_malformed_value_is_refused_by_name(self):
        for raw in ("not json", "[1]", '"gmicloud"', '{"m": "gmicloud"}', '{"m": {}, "n": 3}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, provider_routing.ENV):
                provider_routing.setting({provider_routing.ENV: raw})

    def test_the_proposed_value(self):
        # The slugs, as GET /api/v1/providers gave them on 23 October 2026, fall back nowhere.
        self.assertEqual(ROUTE, {"order": ["gmicloud", "deepinfra", "streamlake"], "allow_fallbacks": False})
        self.assertEqual(provider_routing.setting(ON), provider_routing.PROPOSED)


# ---------------------------------------------------------------------------
# The agent's requests

class Builder:
    """A stand-in for openJiuwen's OpenAIModelClient: its request builder returns the model
    and an extra_body of its own, so a wrapper is seen to keep what was there."""

    def _build_request_params(self, **kwargs):
        return {"model": kwargs["model"], "messages": [], "extra_body": {"cache_salt": "s"}}


class TheAgentsRequests(unittest.TestCase):
    """Planted: every model routed, the request's own extra_body dropped, a wrapper installed
    when off, and the wrapper installed twice."""

    def builder(self) -> type:
        return type("Builder", (Builder,), {})

    def test_the_named_model_alone_gets_the_provider_and_nothing_else_changes(self):
        cls = self.builder()
        self.assertEqual(provider_routing.apply_to_agent(cls, ON), provider_routing.PROPOSED)
        self.assertEqual(cls()._build_request_params(model=DEEPSEEK),
                         {"model": DEEPSEEK, "messages": [], "extra_body": {"cache_salt": "s", "provider": ROUTE}})
        self.assertEqual(cls()._build_request_params(model=HAIKU), Builder()._build_request_params(model=HAIKU))

    def test_off_installs_nothing(self):
        cls = self.builder()
        before = cls._build_request_params
        self.assertEqual(provider_routing.apply_to_agent(cls, {}), {})
        self.assertIs(cls._build_request_params, before)

    def test_installed_once_a_process(self):
        cls = self.builder()
        provider_routing.apply_to_agent(cls, ON)
        once = cls._build_request_params
        provider_routing.apply_to_agent(cls, ON)
        self.assertIs(cls._build_request_params, once)


class TheRunner(unittest.TestCase):
    """`run_browser_task.py` with openJiuwen replaced by stand-ins: it installs the routing
    before the agent is built and records it in the run record. Planted: the record without
    the field, and the wrapper not installed."""

    def run_runner(self, environ: dict) -> tuple[dict, type, str]:
        builder = type("OpenAIModelClient", (Builder,), {})
        settings = types.SimpleNamespace(provider="openrouter", api_key="sk-not-a-key",
                                         api_base="https://openrouter.ai/api/v1", model_name=DEEPSEEK,
                                         mcp_cfg=None, guardrails=None)

        class Runtime:
            def __init__(self, **kwargs):
                pass

            async def ensure_started(self):
                pass

            async def run_browser_task(self, task, session_id, timeout_s):
                return {"ok": True, "final": "done"}

            async def shutdown(self):
                pass

        names = ["openjiuwen", "openjiuwen.harness", "openjiuwen.harness.tools",
                 "openjiuwen.harness.tools.browser_move", "openjiuwen.harness.tools.browser_move.playwright_runtime",
                 "openjiuwen.core", "openjiuwen.core.foundation", "openjiuwen.core.foundation.llm",
                 "openjiuwen.core.foundation.llm.model_clients"]
        stubs = {name: types.ModuleType(name) for name in names}
        config = types.ModuleType("config")
        config.MISSING_API_KEY_MESSAGE = "no key"
        config.build_runtime_settings = lambda: settings
        config.load_repo_dotenv = lambda: True
        runtime = types.ModuleType("runtime")
        runtime.BrowserAgentRuntime = Runtime
        clients = types.ModuleType("openai_model_client")
        clients.OpenAIModelClient = builder
        stubs.update({"openjiuwen.harness.tools.browser_move.playwright_runtime.config": config,
                      "openjiuwen.harness.tools.browser_move.playwright_runtime.runtime": runtime,
                      "openjiuwen.core.foundation.llm.model_clients.openai_model_client": clients})
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, stubs), \
                mock.patch.dict(os.environ, environ), contextlib.redirect_stdout(io.StringIO()) as out:
            os.environ.pop(provider_routing.ENV, None) if provider_routing.ENV not in environ else None
            spec = importlib.util.spec_from_file_location("run_browser_task_under_test", RUNNER)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            record_path = pathlib.Path(tmp) / "run.json"
            with mock.patch.object(module, "openrouter_usage", return_value=None), \
                    mock.patch.object(module, "openrouter_usage_after", return_value=None):
                code = asyncio.run(module.run(types.SimpleNamespace(query="q", session="s", timeout=5,
                                                                    out=str(record_path))))
            self.assertEqual(code, 0, out.getvalue())
            return json.loads(record_path.read_text()), builder, out.getvalue()

    def test_on_it_is_installed_and_recorded(self):
        record, builder, printed = self.run_runner(ON)
        self.assertEqual(record["provider_routing"], ROUTE)
        self.assertIn(f"provider routing: {json.dumps(ROUTE)}", printed)
        self.assertEqual(builder()._build_request_params(model=DEEPSEEK)["extra_body"]["provider"], ROUTE)

    def test_off_nothing_is_installed_and_the_record_says_none(self):
        record, builder, printed = self.run_runner({})
        self.assertIsNone(record["provider_routing"])
        self.assertIn("provider routing: off", printed)
        self.assertIs(builder._build_request_params, Builder._build_request_params)


# ---------------------------------------------------------------------------
# The parse call

class Posted:
    """What `requests.post` gets and gives: the body sent, and a reply as OpenRouter's."""

    def __init__(self, provider="GMICloud"):
        self.bodies, self.provider = [], provider

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.bodies.append(json)
        reply = mock.Mock()
        reply.raise_for_status = lambda: None
        body = {"choices": [{"message": {"content": "a reply"}}],
                "usage": {"cost": 0.0002, "prompt_tokens": 5000, "completion_tokens": 90}}
        if self.provider is not ...:
            body["provider"] = self.provider
        reply.json = lambda: body
        return reply


class TheParseCall(unittest.TestCase):
    """Planted: the provider left out of the body, a provider sent when off, and the serving
    provider not returned."""

    def call(self, model: str, environ: dict, provider="GMICloud") -> tuple:
        posted = Posted(provider)
        with mock.patch.object(parse_probe.requests, "post", posted), mock.patch.dict(os.environ, environ):
            if provider_routing.ENV not in environ:
                os.environ.pop(provider_routing.ENV, None)
            got = parse_probe.call_model("k", model, "the prompt")
        return got, posted.bodies[-1]

    def test_the_body_carries_the_provider_for_the_routed_model_only(self):
        _, routed = self.call(DEEPSEEK, ON)
        self.assertEqual(routed["provider"], ROUTE)
        _, other = self.call(HAIKU, ON)
        self.assertNotIn("provider", other)

    def test_off_the_body_is_what_it_always_was(self):
        _, body = self.call(DEEPSEEK, {})
        self.assertEqual(json.dumps(body, sort_keys=True), json.dumps(
            {"model": DEEPSEEK, "temperature": 0, "usage": {"include": True},
             "messages": [{"role": "user", "content": "the prompt"}]}, sort_keys=True))

    def test_the_serving_provider_is_returned(self):
        self.assertEqual(self.call(DEEPSEEK, ON)[0], ("a reply", 0.0002, {"prompt": 5000, "completion": 90}, "GMICloud"))
        for provider in (..., None, 7):
            with self.subTest(provider=provider):
                self.assertIsNone(self.call(DEEPSEEK, ON, provider)[0][3])

    def test_the_probe_records_the_routing_and_each_calls_provider(self):
        for environ, recorded in ((ON, ROUTE), ({}, None)):
            with self.subTest(on=bool(environ)), tempfile.TemporaryDirectory() as tmp:
                def fake(key, model, prompt):
                    return "no form here", 0.001, None, "GMICloud"
                with mock.patch.object(parse_probe, "call_model", fake), \
                        mock.patch.object(parse_probe, "RESULTS", pathlib.Path(tmp)), \
                        mock.patch.object(plan_probe, "load_key", return_value="fake-key"), \
                        mock.patch.object(plan_probe, "usage", return_value=None), \
                        mock.patch.dict(os.environ, environ), \
                        mock.patch.object(sys, "argv", ["parse_probe.py", "--questions", str(PARAPHRASES),
                                                        "--model", DEEPSEEK]), \
                        contextlib.redirect_stdout(io.StringIO()):
                    if provider_routing.ENV not in environ:
                        os.environ.pop(provider_routing.ENV, None)
                    self.assertEqual(parse_probe.main(), 0)
                written = json.loads(next(pathlib.Path(tmp).glob("parse-probe-*.json")).read_text())
                self.assertEqual(written["provider_routing"], recorded)
                self.assertEqual({row["provider"] for row in written["rows"]}, {"GMICloud"})


# ---------------------------------------------------------------------------
# The suite

class TheSuite(unittest.TestCase):
    """Planted: the payload without the routing, the header line printed when off, a
    malformed setting run, the parse's provider not recorded, the agent's providers not
    recorded, no void under routing, and a void without routing."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.tasks = keyed_tasks(pathlib.Path(self.folder.name))

    def batch(self, environ: dict, *argv: str, call_model=None):
        with mock.patch.object(parse_probe, "call_model", call_model or replying(served="GMICloud")), \
                mock.patch.object(plan_probe, "load_key", return_value="fake-key"), \
                mock.patch.dict(os.environ, {"MODEL_NAME": DEEPSEEK, **environ}):
            if provider_routing.ENV not in environ:
                os.environ.pop(provider_routing.ENV, None)
            run = run_suite("--tasks", str(self.tasks), "--repeats", "1", "--only", "apparel-cheapest-target",
                            *argv, page=thornwood_page())
        self.addCleanup(run.owner.cleanup)
        payload = json.loads((run.batch / "suite.json").read_text()) if run.batch else None
        return run, payload

    def test_the_payload_records_the_routing_on_and_off(self):
        run, payload = self.batch(ON, "--box", "--parser", "model")
        self.assertEqual(run.code, 0, run.out)
        self.assertEqual(payload["provider_routing"], {"agent": ROUTE, "parser": ROUTE})
        run, payload = self.batch({}, "--box", "--parser", "model")
        self.assertEqual(payload["provider_routing"], {"agent": None, "parser": None})
        run, payload = self.batch(ON)
        self.assertEqual(payload["provider_routing"], {"agent": ROUTE, "parser": None})

    def test_the_header_says_it_only_when_on(self):
        line = f"provider routing: agent {json.dumps(ROUTE)}, parser {json.dumps(ROUTE)}"
        run, _ = self.batch(ON, "--box", "--parser", "model", "--dry-run")
        self.assertIn(line, run.out)
        run, _ = self.batch({}, "--box", "--parser", "model", "--dry-run")
        self.assertNotIn("provider routing", run.out)

    def test_a_malformed_setting_refuses_before_anything_runs(self):
        run, payload = self.batch({provider_routing.ENV: "{not json"}, "--box", "--parser", "model")
        self.assertEqual((run.code, run.calls, payload), (2, 0, None))
        self.assertIn(provider_routing.ENV, run.out)

    def test_each_run_records_the_parses_provider(self):
        run, payload = self.batch(ON, "--box", "--parser", "model")
        row = payload["rows"][0]
        record = json.loads((run.batch / "apparel-cheapest-target-1.json").read_text())
        self.assertEqual((row["parse_provider"], record["parse_provider"]), ("GMICloud", "GMICloud"))

    def test_under_routing_a_failed_parse_call_voids_the_slot(self):
        def down(key, model, prompt):
            raise requests.exceptions.HTTPError("404 Client Error: no allowed providers are available")

        run, payload = self.batch(ON, "--box", "--parser", "model", call_model=down)
        row = payload["rows"][0]
        self.assertEqual((run.code, run.calls, row["verdict"], row["log"]), (0, 0, "void", None))
        self.assertIn("the model call failed", row["why"])
        # voids.py classes the slot void, by its own rule for a slot with no run record, so the
        # chain re-runs it once at the end.
        slots = voids.batch_runs(run.batch)
        self.assertEqual([(slot.outcome, slot.reason, slot.task, slot.repeat) for slot in slots],
                         [(voids.VOID, "no record", "apparel-cheapest-target", 1)])
        # Without routing the rules decide, as before: the agent runs.
        run, payload = self.batch({}, "--box", "--parser", "model", call_model=down)
        row = payload["rows"][0]
        self.assertEqual((run.calls, row["box"]["parse"]["used"]), (1, "rules"))
        self.assertNotEqual(row["verdict"], "void")

    def test_each_run_records_the_providers_of_the_agents_calls(self):
        log = completion("GMICloud") + completion("GMICloud") + completion("StreamLake")
        owner = tempfile.TemporaryDirectory()
        self.addCleanup(owner.cleanup)
        results = pathlib.Path(owner.name)

        def runner(command, cwd=None, env=None, stdout=None, stderr=None, check=False):
            record = pathlib.Path(command[command.index("--out") + 1])
            record.write_text(json.dumps({"model": DEEPSEEK, "elapsed_s": 1.0, "cost_usd": 0.0, "error": None,
                                          "result": {"ok": True, "final": "Seller A, $10.00"}}))
            stdout.write(log)
            return subprocess.CompletedProcess(command, 0)

        identity = {"agent_core_commit": "a" * 40, "agent_core_patch": "b" * 40}
        with mock.patch.object(sys, "argv", ["suite.py", "--tasks", str(self.tasks), "--repeats", "1",
                                             "--only", "apparel-cheapest-target"]), \
                mock.patch.object(suite, "RESULTS", results), mock.patch.object(suite.subprocess, "run", runner), \
                mock.patch.object(suite, "agent_code_identity", return_value=identity), \
                mock.patch.dict(os.environ, {"MODEL_NAME": DEEPSEEK}), contextlib.redirect_stdout(io.StringIO()):
            os.environ.pop(provider_routing.ENV, None)
            self.assertEqual(suite.main(), 0)
        batch = next(p for p in results.iterdir() if p.is_dir())
        row = json.loads((batch / "suite.json").read_text())["rows"][0]
        self.assertEqual(row["providers"], {"GMICloud": 2, "StreamLake": 1})


# ---------------------------------------------------------------------------
# The log's providers, and the voids an outage leaves

class TheLogsProviders(unittest.TestCase):
    """Planted: providers counted without holding them to the completions."""

    def test_one_provider_per_completion(self):
        text = completion("GMICloud") + completion("StreamLake") + completion("GMICloud")
        self.assertEqual(trace_stats.served_by(text), {"GMICloud": 2, "StreamLake": 1})

    def test_a_completion_without_one_leaves_no_count(self):
        self.assertIsNone(trace_stats.served_by(completion("GMICloud") + completion(None)))
        self.assertIsNone(trace_stats.served_by("no completion at all"))
        # The runner's own line names the provider unquoted, and is not a completion's.
        self.assertIsNone(trace_stats.served_by("provider=openrouter model=deepseek/deepseek-v4-flash\n"))

    def test_the_trace_carries_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = pathlib.Path(tmp) / "run.log"
            log.write_text(completion("DeepInfra") * 2)
            self.assertEqual(trace_stats.stats(log)["providers"], {"DeepInfra": 2})

    def test_the_pilots_logs_where_this_checkout_has_them(self):
        manifest = paths.RESULTS / "pilot-20261023.manifest"
        folders = [line.split("|")[1] for line in (manifest.read_text().splitlines() if manifest.exists() else [])
                   if line.startswith("batch|") and line.split("|")[1]]
        logs = [log for folder in folders for log in pathlib.Path(folder).glob("*.log")]
        if not logs:
            self.skipTest("the pilot's logs are not in this checkout")
        counted = [trace_stats.served_by(log.read_text(errors="replace")) for log in logs]
        self.assertNotIn(None, counted)
        total = {}
        for count in counted:
            for name, n in count.items():
                total[name] = total.get(name, 0) + n
        self.assertEqual(total, {"Relace": 750, "GMICloud": 410, "Parasail": 195, "StreamLake": 147})


class AnOutageIsAVoid(unittest.TestCase):
    """With allow_fallbacks false and every listed provider down, openJiuwen ends the run on
    the provider's error with no final answer, which voids.py classes as void, never as a
    wrong answer. voids.py is not changed: this holds its rule to the case."""

    def test_the_agents_run(self):
        error = ("[181001] model call failed, reason: openAI API async invoke error: NotFoundError: "
                 "Error code: 404 - {'error': {'message': 'No allowed providers are available for the "
                 "selected model.', 'code': 404}}")
        record = {"result": {"ok": False, "final": "", "error": error}, "error": None}
        self.assertEqual(voids.classify(record, "")[:2], (voids.VOID, "provider error"))


if __name__ == "__main__":
    unittest.main()
