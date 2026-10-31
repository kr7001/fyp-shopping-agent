#!/usr/bin/env python3
"""Browser Use transfer-study adapter; frozen block and historical runners are untouched.

The study launcher owns approval, secrets, the shared CallBudget and result writing.
Importing this module neither imports Browser Use nor reads environment credentials.
All provider calls use one guarded raw-HTTP channel, including helper calls. Browser
network requests are restricted by an external Playwright context, not only the
agent's navigation allowlist. This is network confinement, not an access-control
claim about hidden DOM data or data/blob documents.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import hashlib
from functools import wraps
import importlib.metadata
import json
import math
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
from urllib.parse import urlsplit, urlunsplit

PINNED_BROWSER_USE = "0.13.14"
GATED_UA = "Mozilla/5.0 IGRGated/1.0"
OPENROUTER_CHAT = "https://openrouter.ai/api/v1/chat/completions"


def configure_private_runtime():
    """Set before the first Browser Use import, whose modules call load_dotenv."""
    values = {"PYTHON_DOTENV_DISABLED": "1", "ANONYMIZED_TELEMETRY": "false",
              "BROWSER_USE_CLOUD_SYNC": "false", "BROWSER_USE_VERSION_CHECK": "false",
              "BROWSER_USE_CLOUD_HINTS": "false", "BROWSER_USE_CALCULATE_COST": "false",
              "BROWSER_USE_SETUP_LOGGING": "false", "BROWSER_USE_LOGGING_LEVEL": "warning"}
    os.environ.update(values)
    # Optional observability integrations must not export research traces.
    for name in ("LAMINAR_API_KEY", "LMNR_PROJECT_API_KEY", "BROWSER_USE_API_KEY"):
        os.environ.pop(name, None)


def origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("expected an HTTP(S) URL without user information")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.scheme}://{parsed.hostname.lower()}:{port}"


def normalized_url(url: str) -> str:
    """Identity of an observed candidate, retaining its meaningful query string."""
    parsed = urlsplit(url)
    normalized_origin = origin(url)
    return normalized_origin + (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")


def network_allowed(url: str, allowed_origin: str) -> bool:
    try:
        return origin(url) == allowed_origin
    except (ValueError, TypeError):
        return False


class ProductDocument(HTMLParser):
    def __init__(self):
        super().__init__()
        self.product_body = False
        self.product_info = False

    def handle_starttag(self, tag, attrs):
        classes = set(dict(attrs).get("class", "").split())
        if tag == "body" and "catalog-product-view" in classes:
            self.product_body = True
        if "product-info-main" in classes:
            self.product_info = True


def is_product_document(html: str) -> bool:
    parser = ProductDocument()
    parser.feed(html)
    return parser.product_body and parser.product_info


@dataclass
class NavigationRecorder:
    candidate_urls: list[str]
    events: list[dict] = field(default_factory=list)
    opened: set[str] = field(default_factory=set)
    blocked: list[dict] = field(default_factory=list)
    observation_errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.candidates = {normalized_url(url) for url in self.candidate_urls}

    def observe(self, url: str, status: int, html: str, *, main_document: bool, page_id: str):
        try:
            identity = normalized_url(url)
        except ValueError:
            return
        candidate = identity in self.candidates
        product = main_document and 200 <= status < 300 and is_product_document(html)
        counted = candidate and product
        self.events.append({"url": url, "status": status, "main_document": main_document,
                            "page_id": page_id, "candidate": candidate,
                            "product_document": product, "counted": counted})
        if counted:
            self.opened.add(identity)

    def record(self):
        return {"opened": len(self.opened), "opened_urls": sorted(self.opened),
                "navigation_events": self.events, "blocked_requests": self.blocked,
                "observation_errors": self.observation_errors,
                "measurement_valid": not self.observation_errors}


def validate_config(config: dict):
    required = {"query", "start_url", "candidate_urls", "model", "provider",
                "max_input_bytes", "max_output_tokens", "max_steps", "clock_s", "out_dir"}
    absent = required - config.keys()
    if absent:
        raise ValueError("missing runner settings: " + ", ".join(sorted(absent)))
    allowed = origin(config["start_url"])
    if urlsplit(config["start_url"]).scheme != "http":
        raise ValueError("the research shop must use the declared loopback HTTP endpoint")
    if urlsplit(config["start_url"]).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("this runner is restricted to the local research shop")
    if not isinstance(config["query"], str) or not config["query"].strip():
        raise ValueError("query must be nonempty text")
    if not isinstance(config["candidate_urls"], list) or not config["candidate_urls"]:
        raise ValueError("candidate URLs must come from the observed results page")
    if any(origin(url) != allowed for url in config["candidate_urls"]):
        raise ValueError("candidate URL is outside the declared shop origin")
    for name in ("max_input_bytes", "max_output_tokens", "max_steps", "clock_s"):
        if type(config[name]) is not int or config[name] <= 0:
            raise ValueError(f"{name} must be a positive integer")
    failures = config.get("max_failures", 2)
    if type(failures) is not int or not 1 <= failures <= 5:
        raise ValueError("max_failures must be an integer from 1 to 5")
    if not isinstance(config["provider"], dict) or not config["provider"]:
        raise ValueError("explicit provider routing is required")
    if config.get("use_vision", False) is not False:
        raise ValueError("this transfer condition is text-only")
    return allowed


def charge_metadata(payload, status: int):
    usage = payload.get("usage") if isinstance(payload, dict) else None
    cost = usage.get("cost") if isinstance(usage, dict) else None
    known = type(cost) in (float, int) and math.isfinite(cost) and cost >= 0
    return {"status": status, "generation_id": payload.get("id") if isinstance(payload, dict) else None,
            "provider": payload.get("provider") if isinstance(payload, dict) else None,
            "cost_usd": float(cost) if known else None,
            "prompt_tokens": usage.get("prompt_tokens") if isinstance(usage, dict) else None,
            "completion_tokens": usage.get("completion_tokens") if isinstance(usage, dict) else None}


def create_llm(config: dict, guard, api_key: str, role: str = "executor", *, transport=None):
    """Return a native ChatOpenAI using a guarded transport; no token-price estimate is a charge.

    `transport` is an offline test seam. Every actual HTTP attempt reserves before
    sending and settles afterward; SDK automatic retries are disabled. The shared
    guard must permanently block after unknown charge or request failure.
    """
    configure_private_runtime()
    import httpx
    from browser_use import ChatOpenAI
    if not api_key:
        raise ValueError("the verified launcher must supply an API key explicitly")
    if importlib.metadata.version("browser-use") != PINNED_BROWSER_USE:
        raise ValueError("Browser Use version differs from the pinned adapter")

    class GuardedTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.inner = transport or httpx.AsyncHTTPTransport(retries=0)
            self.calls = []

        async def handle_async_request(self, request):
            if str(request.url) != OPENROUTER_CHAT or request.method != "POST":
                raise ValueError("unexpected model endpoint or HTTP method")
            body = json.loads(await request.aread())
            if body.get("model") != config["model"] or body.get("stream", False):
                raise ValueError("unexpected model or streaming request")
            # Pin routing and request provider-reported billing for every helper call.
            body["provider"] = config["provider"]
            body["usage"] = {"include": True}
            body["stream"] = False
            if any(key in body for key in ("plugins", "audio", "modalities")):
                raise ValueError("non-text or plugin requests are not budgeted")
            for message in body.get("messages", []):
                content = message.get("content")
                if content is not None and not isinstance(content, (str, list)):
                    raise ValueError("unexpected message content")
                if isinstance(content, list) and any(part.get("type") != "text" for part in content):
                    raise ValueError("multimodal requests are not budgeted")
            body["max_completion_tokens"] = config["max_output_tokens"]
            body.pop("max_tokens", None)
            prompt_part = {k: v for k, v in body.items() if k not in {"provider", "usage"}}
            prompt_bytes = len(json.dumps(prompt_part, ensure_ascii=False).encode("utf-8"))
            metadata = {"model": config["model"], "prompt_bytes": prompt_bytes,
                        "max_output_tokens": config["max_output_tokens"],
                        "provider": config["provider"], "role": role, "nontext_or_plugins": False}
            reservation = await asyncio.to_thread(guard.before_call, metadata)
            call = {"reservation": reservation, "role": role, "prompt_bytes": prompt_bytes,
                    "request_sha256": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
                    "cost_usd": None, "started_at": time.time()}
            self.calls.append(call)
            forwarded = httpx.Request(request.method, request.url,
                                      headers={k: v for k, v in request.headers.items()
                                               if k.lower() != "content-length"},
                                      json=body, extensions=request.extensions)
            settled = False
            try:
                response = await self.inner.handle_async_request(forwarded)
                content = await response.aread()
                payload = json.loads(content)
                call.update(charge_metadata(payload, response.status_code))
                settled = True
                await asyncio.to_thread(guard.after_call, reservation, response_json=payload,
                                        error=f"HTTP_{response.status_code}" if response.status_code >= 400 else None)
                return response
            except BaseException as error:
                call["error_type"] = type(error).__name__
                if not settled:
                    await asyncio.to_thread(guard.after_call, reservation, error=type(error).__name__)
                raise
            finally:
                call["finished_at"] = time.time()

        async def aclose(self):
            await self.inner.aclose()

    accounted_transport = GuardedTransport()
    client = httpx.AsyncClient(transport=accounted_transport, timeout=config.get("llm_timeout", 120),
                               follow_redirects=False, trust_env=False)
    llm = ChatOpenAI(model=config["model"], api_key=api_key,
                     base_url="https://openrouter.ai/api/v1", http_client=client,
                     temperature=config.get("temperature", 0.2),
                     frequency_penalty=config.get("frequency_penalty", 0.1),
                     top_p=config.get("top_p"), max_retries=0,
                     max_completion_tokens=config["max_output_tokens"],
                     timeout=config.get("llm_timeout", 120))
    llm.igr_calls = accounted_transport.calls
    llm.igr_http_client = client
    return llm


async def close_llm(llm):
    client = getattr(llm, "igr_http_client", None)
    if client:
        await client.aclose()


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def confined_proxy(allowed_origin: str, recorder: NavigationRecorder):
    """Check every browser HTTP request, including redirects Playwright does not re-route.

    Chrome is explicitly forbidden to bypass the proxy for loopback. CONNECT and
    WebSocket upgrades are denied: this study has one plain-HTTP local shop. The
    proxy never follows redirects itself; each redirected browser request is checked
    again before any destination connection is opened.
    """
    hop_headers = {"connection", "proxy-connection", "proxy-authorization", "keep-alive",
                   "transfer-encoding", "upgrade", "host", "content-length"}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def deny(self, kind):
            recorder.blocked.append({"url": self.path, "resource_type": kind,
                                     "boundary": "loopback_proxy"})
            self.send_response(403); self.send_header("Content-Length", "0"); self.end_headers()

        def do_CONNECT(self):
            self.deny("connect")

        def forward(self):
            if not network_allowed(self.path, allowed_origin) or self.headers.get("Upgrade"):
                self.deny("http"); return
            parsed = urlsplit(self.path)
            connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=60)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 4_000_000:
                    self.deny("oversized_request"); return
                body = self.rfile.read(length) if length else None
                headers = {k: v for k, v in self.headers.items() if k.lower() not in hop_headers}
                headers["Host"] = parsed.netloc
                path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
                connection.request(self.command, path, body=body, headers=headers)
                response = connection.getresponse()
                data = response.read()
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in hop_headers:
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)
            except Exception:
                try:
                    self.send_error(502, "local research proxy request failed")
                except Exception:
                    pass
            finally:
                connection.close()

        do_GET = do_POST = do_HEAD = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = forward

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown(); server.server_close(); thread.join()


@asynccontextmanager
async def research_browser(config: dict, recorder: NavigationRecorder):
    """Own the browser, network restrictions and measurements outside the agent."""
    from playwright.async_api import async_playwright
    allowed = validate_config(config)
    pending = set()
    page_ids = {}
    with tempfile.TemporaryDirectory(prefix="igr-browser-use-") as profile, confined_proxy(allowed, recorder) as proxy_url:
        async with async_playwright() as playwright:
            port = unused_port()
            context = await playwright.chromium.launch_persistent_context(
                profile, executable_path=config.get("browser_executable",
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                headless=True, user_agent=GATED_UA, viewport={"width": 1280, "height": 720},
                service_workers="block", accept_downloads=False, chromium_sandbox=True,
                proxy={"server": proxy_url, "bypass": "<-loopback>"},
                args=[f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1",
                      "--disable-background-networking", "--disable-component-update", "--disable-sync",
                      "--proxy-bypass-list=<-loopback>"])

            async def route(request_route):
                request = request_route.request
                if network_allowed(request.url, allowed):
                    await request_route.continue_()
                else:
                    recorder.blocked.append({"url": request.url, "resource_type": request.resource_type})
                    await request_route.abort("blockedbyclient")

            await context.route("**/*", route)
            if not hasattr(context, "route_web_socket"):
                await context.close()
                raise ValueError("Playwright must support context-level WebSocket interception")

            async def deny_socket(socket_route):
                recorder.blocked.append({"url": socket_route.url, "resource_type": "websocket"})
                await socket_route.close()

            await context.route_web_socket("**/*", deny_socket)

            async def observe_response(response):
                request = response.request
                if request.resource_type != "document":
                    return
                try:
                    frame = request.frame
                    page = frame.page
                    if frame != page.main_frame:
                        return
                    page_id = page_ids.setdefault(page, str(len(page_ids) + 1))
                    html = await response.text() if 200 <= response.status < 300 else ""
                    recorder.observe(response.url, response.status, html,
                                     main_document=True, page_id=page_id)
                except Exception as error:
                    # Do not silently turn a failed measurement into zero openings.
                    recorder.observation_errors.append(type(error).__name__)

            def response_event(response):
                task = asyncio.create_task(observe_response(response))
                pending.add(task)
                task.add_done_callback(pending.discard)

            context.on("response", response_event)
            try:
                yield context, f"http://127.0.0.1:{port}"
            finally:
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                await context.close()


async def native_select_state(browser_session, index: int, *, descendants: bool = True):
    """Read ordinary DOM option state without fixture data or hidden price tables."""
    node = await browser_session.get_element_by_index(index)
    if node is None:
        return None
    session = await browser_session.get_or_create_cdp_session()
    resolved = await session.cdp_client.send.DOM.resolveNode(
        params={"backendNodeId": node.backend_node_id}, session_id=session.session_id)
    object_id = resolved.get("object", {}).get("objectId")
    if not object_id:
        raise RuntimeError("could not inspect dropdown DOM state")
    response = await session.cdp_client.send.Runtime.callFunctionOn(
        params={"objectId": object_id, "returnByValue": True,
                "arguments": [{"value": descendants}],
                "functionDeclaration": """function(descendants) {
                    const select = this.tagName.toLowerCase() === 'select' ? this :
                        (descendants ? this.querySelector('select') : null);
                    if (!select) return null;
                    const disabled = select.matches(':disabled');
                    return {disabled, options: Array.from(select.options).map(option => ({
                        text: option.text.trim(), value: option.value,
                        selected: option.selected,
                        disabled: disabled || option.matches(':disabled')
                    }))};
                }"""}, session_id=session.session_id)
    if response.get("exceptionDetails"):
        raise RuntimeError("dropdown DOM inspection failed")
    return response.get("result", {}).get("value")


def enforce_native_dropdown_state(tools):
    """Repair 0.13.14 built-in dropdown tools symmetrically for both study arms.

    Upstream omits disabled flags and can programmatically select disabled options.
    These wrappers expose DOM disabled state and reject those selections, including
    disabled select/optgroup ancestors. They do not sandbox arbitrary evaluate().
    """
    from browser_use.agent.views import ActionResult

    def describe(state):
        text = "Native dropdown DOM state (disabled options cannot be chosen):\n" + json.dumps(state, ensure_ascii=False)
        return ActionResult(extracted_content=text, long_term_memory=text,
                            include_extracted_content_only_once=True)

    for name in ("dropdown_options", "select_dropdown"):
        action = tools.registry.registry.actions[name]
        original = action.function
        def wrap(original, name):
            @wraps(original)
            async def checked(*args, **kwargs):
                params, browser = kwargs["params"], kwargs["browser_session"]
                state = await native_select_state(browser, params.index)
                if state is not None:
                    if name == "dropdown_options":
                        return describe(state)
                    target = params.text.lower()
                    match = next((option for option in state["options"]
                                  if option["text"].lower() == target or option["value"].lower() == target), None)
                    if match is None:
                        return ActionResult(error="Option was not found in the inspected native dropdown.")
                    if state["disabled"] or match["disabled"]:
                        return ActionResult(error="Cannot select a disabled option or disabled dropdown.")
                return await original(*args, **kwargs)
            return checked
        action.function = wrap(original, name)

    # Native click(select) invokes a closure directly, bypassing the registry.
    # Wrap its stored index handler so action re-registration cannot undo the fix.
    original_click = tools._click_by_index
    @wraps(original_click)
    async def checked_click(params, browser_session):
        state = await native_select_state(browser_session, params.index, descendants=False)
        if state is not None:
            return describe(state)
        return await original_click(params, browser_session)
    tools._click_by_index = checked_click
    return tools


def scope_evaluate_calls(tools):
    """Keep native script results/errors, but make local declarations per-call.

    Native CDP Runtime.evaluate keeps top-level lexical bindings between calls.
    A corrected script can therefore fail after an earlier `const` declaration.
    Direct eval in a fresh function preserves script completion values, IIFEs and
    promises without retrying code or repairing invalid top-level return syntax.
    This is a declared adapter compatibility change, not a JavaScript sandbox.
    """
    validate = tools._validate_and_fix_javascript
    def scoped(code):
        return "(function () { return eval(" + json.dumps(validate(code)) + "); }).call(window)"
    tools._validate_and_fix_javascript = scoped
    tools.registry.registry.actions["evaluate"].description += (
        " Each call has fresh local variables. Use an IIFE for return statements. "
        "Global-object properties and page state can persist between calls.")
    return tools


def research_tools():
    """Keep native browser tools while denying host-file upload and vision input.

    Browser Use treats CDP attachments as remote, so its upload_file action skips
    the local available_file_paths check. Our browser is physically local: remove
    that action explicitly. Native read/write_file remain within the fresh agent
    workspace with an empty external-file allowlist.
    """
    configure_private_runtime()
    from browser_use import Tools
    return scope_evaluate_calls(enforce_native_dropdown_state(Tools(exclude_actions=["upload_file", "screenshot"])))


async def run_trial(config: dict, guard=None, api_key: str | None = None, *, scripted_llm=None):
    """Execute one bounded local-shop trial. Scripted model is only for offline checks."""
    validate_config(config)
    configure_private_runtime()
    if importlib.metadata.version("browser-use") != PINNED_BROWSER_USE:
        raise ValueError("Browser Use version differs from the pinned adapter")
    from browser_use import Agent, Browser
    out_dir = Path(config["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    if scripted_llm is None and guard is None:
        raise ValueError("paid execution requires the launcher's shared spending guard")
    llm = scripted_llm or create_llm(config, guard, api_key)
    recorder = NavigationRecorder(config["candidate_urls"])
    started = time.monotonic()
    record = {"scaffold": "browser-use", "browser_use_version": PINNED_BROWSER_USE,
              "query": config["query"], "answer": None, "outcome": "failed",
              "model": config["model"], "provider_routing": config["provider"],
              "offline_scripted": scripted_llm is not None,
              "dropdown_semantics": "native-disabled-state-v1",
              "evaluate_semantics": "fresh-local-script-scope-v1",
              "settings": {k: config[k] for k in ("start_url", "model", "provider", "temperature",
                           "frequency_penalty", "top_p", "max_input_bytes", "max_output_tokens",
                           "max_steps", "max_failures", "clock_s", "llm_timeout", "browser_executable") if k in config}}
    record["settings"]["max_failures"] = config.get("max_failures", 2)
    agent = browser = None
    try:
        async with research_browser(config, recorder) as (context, cdp_url):
            record["browser_version"] = context.browser.version
            browser = Browser(cdp_url=cdp_url, is_local=False, use_cloud=False,
                              allowed_domains=[config["start_url"].split("/", 3)[0] + "//" + urlsplit(config["start_url"]).netloc],
                              user_agent=GATED_UA, keep_alive=True,
                              enable_default_extensions=False, captcha_solver=False,
                              accept_downloads=False, permissions=[])
            agent = Agent(task=config["query"], llm=llm, browser=browser, tools=research_tools(),
                          page_extraction_llm=llm, fallback_llm=None, judge_llm=llm,
                          use_judge=False, use_vision=False, calculate_cost=False,
                          use_thinking=True, enable_planning=True, message_compaction=True,
                          max_actions_per_step=5, max_failures=config.get("max_failures", 2),
                          llm_timeout=config.get("llm_timeout", 120), step_timeout=180,
                          final_response_after_failure=False, generate_gif=False,
                          available_file_paths=[], file_system_path=str(out_dir / "agent-files"),
                          save_conversation_path=str(out_dir / "conversation"),
                          enable_signal_handler=False,
                          initial_actions=[{"navigate": {"url": config["start_url"]}}],
                          directly_open_url=False)
            history = await asyncio.wait_for(agent.run(max_steps=config["max_steps"]), config["clock_s"])
            history.save_to_file(out_dir / "history.json")
            record["answer"] = history.final_result()
            record["outcome"] = "answered" if history.is_done() and isinstance(record["answer"], str) else "failed"
            record["steps"] = len(history.history)
            record["agent_errors"] = history.errors()
            await browser.stop()
            browser = None
    except asyncio.TimeoutError:
        record["outcome"] = "timeout"
    except Exception as error:
        record["error_type"] = type(error).__name__
        # Details belong to private launcher logs, not an error that might echo a key.
    finally:
        if agent is not None:
            try:
                agent.history.save_to_file(out_dir / "history.json")
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.stop()
            except Exception:
                pass
        await close_llm(llm)
        record["elapsed_s"] = time.monotonic() - started
        record["trace"] = recorder.record()
        record["calls"] = list(getattr(llm, "igr_calls", []))
        costs = [call.get("cost_usd") for call in record["calls"]]
        record["cost_usd"] = (0.0 if scripted_llm is not None else
                              sum(costs) if costs and all(c is not None for c in costs) else None)
        if recorder.observation_errors:
            record["measurement_status"] = "invalid"
        else:
            record["measurement_status"] = "complete"
    return record
