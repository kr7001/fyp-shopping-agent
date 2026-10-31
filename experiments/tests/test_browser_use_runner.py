"""Adapter tests never use a provider key or make a paid model call.

The browser integration case is opt-in (IGR_BROWSER_USE_INTEGRATION=1), uses two
loopback servers and the installed local Chrome. Its expected behavior is scripted,
not supplied by an LLM, and is excluded from every research result.
"""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/runners"))
import browser_use_runner as runner

PRODUCT = '<html><body class="catalog-product-view"><div class="product-info-main"><h1>Test tee</h1><select id="size"><option>M</option></select><span id="price">12.00</span></div></body></html>'
VARIANT_PRODUCT = '''<html><body class="catalog-product-view"><div class="product-info-main"><h1>Variant test tee</h1><label for="size">Size</label><select id="size" onchange="setTimeout(() => document.querySelector('#price').textContent = this.value === 'M' ? '17.90' : '12.00', 1000)"><option value="S">S</option><option value="M">M</option></select><p>Variant price: <span id="price">12.00</span></p></div></body></html>'''
SOFT404 = '<html><body class="cms-noroute-index"><h1>Not found</h1></body></html>'


class Metrics(unittest.TestCase):
    def test_counts_candidate_document_once_across_tabs_and_repeated_visits(self):
        recorder = runner.NavigationRecorder(['http://localhost:7770/p.html'])
        for page_id in ['1', '2', '1']:
            recorder.observe('http://localhost:7770/p.html#section', 200, PRODUCT,
                             main_document=True, page_id=page_id)
        self.assertEqual(recorder.record()['opened'], 1)
        self.assertEqual(len(recorder.events), 3)

    def test_rejects_soft404_hard404_category_non_candidate_and_subframe(self):
        recorder = runner.NavigationRecorder(['http://localhost:7770/p.html'])
        for status, html, main, url in [
                (200, SOFT404, True, 'http://localhost:7770/p.html'),
                (404, PRODUCT, True, 'http://localhost:7770/p.html'),
                (200, '<body class="catalog-category-view">', True, 'http://localhost:7770/p.html'),
                (200, PRODUCT, True, 'http://localhost:7770/category.html'),
                (200, PRODUCT, False, 'http://localhost:7770/p.html')]:
            recorder.observe(url, status, html, main_document=main, page_id='1')
        self.assertEqual(recorder.record()['opened'], 0)

    def test_origin_is_exact_including_port_and_scheme(self):
        allowed = runner.origin('http://localhost:7770/start')
        self.assertTrue(runner.network_allowed('http://localhost:7770/p', allowed))
        for url in ['http://localhost:7771/p', 'https://localhost:7770/p',
                    'https://example.com', 'data:text/html,hi', 'file:///tmp/a',
                    'http://localhost:7770@evil.invalid/p']:
            self.assertFalse(runner.network_allowed(url, allowed))

    def test_query_parameters_are_not_discarded_from_product_identity(self):
        recorder = runner.NavigationRecorder(['http://localhost:7770/p?id=1'])
        recorder.observe('http://localhost:7770/p?id=2', 200, PRODUCT, main_document=True, page_id='1')
        self.assertEqual(recorder.record()['opened'], 0)

    def test_missing_or_nonnumeric_cost_is_unknown_not_zero(self):
        for payload in [{}, {'usage': {}}, {'usage': {'cost': None}},
                        {'usage': {'cost': '0.1'}}, {'usage': {'cost': float('nan')}}]:
            self.assertIsNone(runner.charge_metadata(payload, 200)['cost_usd'])
        self.assertEqual(runner.charge_metadata({'usage': {'cost': 0}}, 200)['cost_usd'], 0)

    def test_runtime_disables_dotenv_and_telemetry(self):
        runner.configure_private_runtime()
        self.assertEqual(os.environ['PYTHON_DOTENV_DISABLED'], '1')
        self.assertEqual(os.environ['ANONYMIZED_TELEMETRY'], 'false')
        self.assertEqual(os.environ['BROWSER_USE_CLOUD_SYNC'], 'false')


HAVE_PACKAGE = importlib.util.find_spec('browser_use') is not None


class FakeGuard:
    def __init__(self):
        self.before, self.after, self.blocked = [], [], False

    def before_call(self, metadata):
        if self.blocked:
            raise RuntimeError('unknown charge blocks the next call')
        self.before.append(metadata)
        return str(len(self.before))

    def after_call(self, reservation, response_json=None, error=None):
        self.after.append((reservation, response_json, error))
        usage = response_json.get('usage', {}) if response_json else {}
        if error or type(usage.get('cost')) not in (int, float):
            self.blocked = True
            raise RuntimeError('unknown charge')


def config(base='http://localhost:7770', out_dir='/tmp/offline-browser-use-test'):
    return {'query': 'Read the product price.', 'start_url': base + '/start',
            'candidate_urls': [base + '/product', base + '/missing'],
            'model': 'deepseek/deepseek-v4-flash',
            'provider': {'only': ['example-provider'], 'allow_fallbacks': False,
                         'max_price': {'prompt': 1, 'completion': 1, 'request': 0}},
            'temperature': 0.2, 'frequency_penalty': 0.1,
            'max_input_bytes': 100000, 'max_output_tokens': 1000,
            'max_steps': 3, 'clock_s': 90, 'out_dir': out_dir}


@unittest.skipUnless(HAVE_PACKAGE, 'isolated pinned Browser Use environment required')
class Transport(unittest.IsolatedAsyncioTestCase):
    def test_native_registry_has_no_host_upload_or_screenshot(self):
        tools = runner.research_tools()
        actions = tools.registry.registry.actions
        self.assertNotIn('upload_file', actions)
        self.assertNotIn('screenshot', actions)
        for needed in ['select_dropdown', 'dropdown_options', 'read_file', 'write_file', 'evaluate']:
            self.assertIn(needed, actions)

    async def test_native_model_captures_raw_charge_and_pins_every_request(self):
        import httpx
        runner.configure_private_runtime()
        from browser_use.llm.messages import UserMessage
        guard, received = FakeGuard(), []

        def respond(request):
            body = json.loads(request.content); received.append(body)
            return httpx.Response(200, json={'id': 'gen-offline', 'object': 'chat.completion',
                'created': 1, 'model': body['model'], 'provider': 'test-provider',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '12'}, 'finish_reason': 'stop'}],
                'usage': {'cost': .0123, 'prompt_tokens': 12, 'completion_tokens': 1, 'total_tokens': 13}})

        cfg = config()
        llm = runner.create_llm(cfg, guard, 'offline-fake-key', transport=httpx.MockTransport(respond))
        try:
            for _ in range(2):
                result = await llm.ainvoke([UserMessage(content='price?')])
                self.assertEqual(result.completion, '12')
            self.assertEqual(len(guard.before), 2)
            self.assertEqual(len(guard.after), 2)
            self.assertEqual([c['cost_usd'] for c in llm.igr_calls], [.0123, .0123])
            self.assertEqual(llm.igr_calls[0]['generation_id'], 'gen-offline')
            self.assertTrue(all(b['provider'] == cfg['provider'] for b in received))
            self.assertTrue(all(b['usage'] == {'include': True} for b in received))
            self.assertTrue(all(b['max_completion_tokens'] == 1000 for b in received))
            self.assertEqual(llm.max_retries, 0)
        finally:
            await runner.close_llm(llm)

    async def test_parser_preserves_single_user_message_and_omits_optional_sampling(self):
        import httpx
        runner.configure_private_runtime()
        from browser_use.llm.messages import UserMessage
        received = []
        def respond(request):
            body = json.loads(request.content); received.append(body)
            return httpx.Response(200, json={'id': 'gen-parser', 'object': 'chat.completion',
                'created': 1, 'model': body['model'], 'provider': 'test-provider',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '{}'}, 'finish_reason': 'stop'}],
                'usage': {'cost': 0, 'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}})
        cfg = config(); cfg.update(temperature=0, frequency_penalty=None, top_p=None)
        llm = runner.create_llm(cfg, FakeGuard(), 'offline-fake-key', role='parser', transport=httpx.MockTransport(respond))
        try:
            await llm.ainvoke([UserMessage(content='original parser prompt')])
            self.assertEqual(received[0]['messages'], [{'role': 'user', 'content': 'original parser prompt'}])
            self.assertEqual(received[0]['temperature'], 0)
            for key in ['frequency_penalty', 'top_p', 'response_format', 'tools']:
                self.assertNotIn(key, received[0])
        finally:
            await runner.close_llm(llm)

    async def test_unknown_cost_stops_before_another_network_request(self):
        import httpx
        runner.configure_private_runtime()
        from browser_use.llm.messages import UserMessage
        guard, requests = FakeGuard(), []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={'choices': [], 'usage': {'prompt_tokens': 2}})

        llm = runner.create_llm(config(), guard, 'offline-fake-key', transport=httpx.MockTransport(respond))
        try:
            for _ in range(2):
                with self.assertRaises(Exception):
                    await llm.ainvoke([UserMessage(content='price?')])
            self.assertEqual(len(requests), 1)
            self.assertIsNone(llm.igr_calls[0]['cost_usd'])
            self.assertTrue(guard.blocked)
        finally:
            await runner.close_llm(llm)

    async def test_http_error_with_zero_charge_blocks_subsequent_attempt(self):
        import httpx
        runner.configure_private_runtime()
        from browser_use.llm.messages import UserMessage
        guard, requests = FakeGuard(), []
        def respond(request):
            requests.append(request)
            return httpx.Response(429, json={'error': {'message': 'offline limit'}, 'usage': {'cost': 0}})
        llm = runner.create_llm(config(), guard, 'offline-fake-key', transport=httpx.MockTransport(respond))
        try:
            for _ in range(2):
                with self.assertRaises(Exception):
                    await llm.ainvoke([UserMessage(content='price?')])
            self.assertEqual(len(requests), 1)
            self.assertEqual(guard.after[0][2], 'HTTP_429')
            self.assertEqual(llm.igr_calls[0]['status'], 429)
            self.assertEqual(llm.igr_calls[0]['cost_usd'], 0)
        finally:
            await runner.close_llm(llm)

    async def test_transport_exception_settles_unknown_and_never_retries(self):
        import httpx
        runner.configure_private_runtime()
        from browser_use.llm.messages import UserMessage
        guard = FakeGuard()

        def respond(request):
            raise httpx.ConnectError('offline failure')

        llm = runner.create_llm(config(), guard, 'offline-fake-key', transport=httpx.MockTransport(respond))
        try:
            with self.assertRaises(Exception):
                await llm.ainvoke([UserMessage(content='price?')])
            self.assertEqual(len(guard.before), 1)
            self.assertEqual(len(guard.after), 1)
            self.assertTrue(guard.blocked)
        finally:
            await runner.close_llm(llm)


@contextmanager
def local_shop():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get('User-Agent')))
            if self.path == '/redirect':
                self.send_response(302); self.send_header('Location', self.server.redirect_target); self.end_headers(); return
            body = PRODUCT if self.path == '/product' else VARIANT_PRODUCT if self.path == '/variant' else SOFT404 if self.path == '/missing' else '<html><body><a href="/product">Test tee</a></body></html>'
            self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers(); self.wfile.write(body.encode())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', server, requests
    finally:
        server.shutdown(); server.server_close(); thread.join()


INTEGRATION = HAVE_PACKAGE and os.environ.get('IGR_BROWSER_USE_INTEGRATION') == '1'


@unittest.skipUnless(INTEGRATION, 'opt-in offline local-browser integration check')
class BrowserBoundary(unittest.IsolatedAsyncioTestCase):
    async def test_product_counts_new_tabs_fetch_redirect_and_gated_user_agent(self):
        with local_shop() as (base, server, calls), local_shop() as (other, _, forbidden):
            server.redirect_target = other + '/escape'
            cfg = config(base)
            recorder = runner.NavigationRecorder(cfg['candidate_urls'])
            async with runner.research_browser(cfg, recorder) as (context, _):
                page = context.pages[0]
                await page.goto(base + '/start')
                await page.goto(base + '/product')
                await page.goto(base + '/missing')
                tab = await context.new_page(); await tab.goto(base + '/product')
                await tab.evaluate('(url) => fetch(url).catch(() => null)', other + '/fetch')
                try:
                    response = await tab.goto(base + '/redirect')
                    self.assertEqual(response.status, 403)
                except Exception as error:
                    self.assertIn('ERR_HTTP_RESPONSE_CODE_FAILURE', str(error))
                await asyncio.sleep(.2)
            self.assertEqual(recorder.record()['opened'], 1)
            self.assertTrue(any(e['url'] == base + '/missing' and not e['counted'] for e in recorder.events))
            self.assertEqual(forbidden, [])
            self.assertTrue(all(ua == runner.GATED_UA for _, ua in calls))
            self.assertFalse(recorder.observation_errors)
            self.assertGreaterEqual(len(recorder.blocked), 2)

    async def test_native_variant_selection_waits_and_reads_updated_price(self):
        runner.configure_private_runtime()
        from browser_use.llm.views import ChatInvokeCompletion
        class Scripted:
            model = 'offline-scripted'
            provider = 'offline'
            name = 'offline-scripted'
            _verified_api_keys = True
            def __init__(self, url): self.url, self.n, self.observed = url, 0, []
            async def ainvoke(self, messages, output_format=None, **kwargs):
                self.n += 1
                current = '\n'.join(str(message.content) for message in messages)
                self.observed.append(current)
                if self.n == 1:
                    action = {'navigate': {'url': self.url}}
                elif self.n == 2:
                    match = re.search(r'\[(\d+)\]<select\b', current)
                    if not match:
                        raise AssertionError('native browser state did not expose the select index')
                    action = {'select_dropdown': {'index': int(match.group(1)), 'text': 'M'}}
                elif self.n == 3:
                    action = {'wait': {'seconds': 2}}
                else:
                    matches = re.findall(r'Variant price:\s*(\d+\.\d+)', current)
                    match = matches[-1] if matches else None
                    if not match:
                        raise AssertionError('native browser state did not expose the resulting price')
                    action = {'done': {'text': match, 'success': True}}
                payload = {'evaluation_previous_goal': 'Scripted test', 'memory': 'Offline only',
                           'next_goal': 'Read the selected variant price', 'action': [action]}
                return ChatInvokeCompletion(completion=output_format.model_validate(payload), usage=None)
        with local_shop() as (base, _, calls), tempfile.TemporaryDirectory() as directory:
            cfg = config(base, directory)
            cfg.update(candidate_urls=[base + '/variant'], max_steps=4,
                       query='Select size M and report its updated price.')
            model = Scripted(base + '/variant')
            result = await runner.run_trial(cfg, scripted_llm=model)
            self.assertEqual(result['outcome'], 'answered', result)
            self.assertEqual(result['answer'], '17.90', result)
            self.assertEqual(result['trace']['opened'], 1)
            self.assertEqual(result['calls'], [])
            self.assertEqual(result['cost_usd'], 0)
            history = json.loads(Path(directory, 'history.json').read_text())
            serialized = json.dumps(history)
            self.assertIn('select_dropdown', serialized)
            self.assertIn('Selected option', serialized)
            self.assertIn('wait', serialized)
            self.assertTrue(all(ua == runner.GATED_UA for _, ua in calls))

    async def test_native_agent_runs_with_a_scripted_model_and_no_provider(self):
        runner.configure_private_runtime()
        from browser_use.llm.views import ChatInvokeCompletion
        class Scripted:
            model = 'offline-scripted'
            provider = 'offline'
            name = 'offline-scripted'
            _verified_api_keys = True
            def __init__(self, base, other): self.base, self.other, self.n = base, other, 0
            async def ainvoke(self, messages, output_format=None, **kwargs):
                self.n += 1
                actions = [
                    {'navigate': {'url': self.base + '/product', 'new_tab': True}},
                    {'evaluate': {'code': 'Promise.all([' + ','.join('fetch(' + json.dumps(url) + ').catch(() => null)' for url in [self.other + '/fetch', self.base + '/redirect']) + ']).then(() => \"checked\")'}},
                    {'done': {'text': '12.00', 'success': True}}]
                action = actions[min(self.n - 1, len(actions) - 1)]
                payload = {'evaluation_previous_goal': 'Scripted test', 'memory': 'Offline only',
                           'next_goal': 'Complete test', 'action': [action]}
                return ChatInvokeCompletion(completion=output_format.model_validate(payload), usage=None)
        with local_shop() as (base, server, calls), local_shop() as (other, _, forbidden), tempfile.TemporaryDirectory() as directory:
            server.redirect_target = other + '/escape'
            cfg = config(base, directory)
            result = await runner.run_trial(cfg, scripted_llm=Scripted(base, other))
            self.assertEqual(result['outcome'], 'answered', result)
            self.assertEqual(result['answer'], '12.00')
            self.assertEqual(result['trace']['opened'], 1)
            self.assertEqual(forbidden, [])
            self.assertGreaterEqual(len(result['trace']['blocked_requests']), 2)
            self.assertTrue(any(e.get('boundary') == 'loopback_proxy' for e in result['trace']['blocked_requests']))
            self.assertEqual(result['calls'], [])
            self.assertEqual(result['cost_usd'], 0)
            self.assertTrue(Path(directory, 'history.json').exists())
            self.assertTrue(all(ua == runner.GATED_UA for _, ua in calls))


if __name__ == '__main__':
    unittest.main()
