#!/usr/bin/env python3
"""Product pages a Browser Use trial fetched by script, recorded beside its navigation count.

Added 2 November 2026 for the fresh market (notes/fresh-market-2-nov/analysis-plan-A.md).
The cohort's counter, `browser_use_runner.NavigationRecorder`, counts a listing only when a
main frame navigates to it, and the 29 October report found an agent that fetched every
product page through JavaScript instead, which no navigation count sees. This adds one more
listener to the same browser context, in both arms: every response for one of the results
page's candidate URLs that arrives by fetch or XMLHttpRequest, or as a document in a
subframe, is recorded with its status and whether its body is a product page.

It is passive. It sends nothing to the page, the agent never sees it, and it reads only
responses the browser already received. Its own failures go to its own `errors` list, never
to the navigation recorder's, whose errors would invalidate the trial. The adapter file
stays byte-identical: `recording` swaps the adapter's `research_browser` for one trial and
always puts the original back.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager

from browser_use_runner import is_product_document, normalized_url

# Resource types a page script produces. A main-frame document is a navigation, which the
# cohort's counter already counts; a document in a subframe is loaded by the page, not the user.
SCRIPT_TYPES = ("fetch", "xhr")
DEFINITION = ("unique results-page candidate URLs whose 2xx response, received by fetch, "
              "XMLHttpRequest or a subframe document, is a product page; navigations excluded")


class ScriptFetches:
    """Candidate product pages reached other than by main-frame navigation, in one trial."""

    def __init__(self, candidate_urls):
        self.candidates = {normalized_url(url) for url in candidate_urls}
        self.events = []
        self.fetched = set()
        self.errors = []

    async def observe(self, response):
        try:
            identity = normalized_url(response.url)
        except (ValueError, TypeError):
            return
        if identity not in self.candidates:
            return
        try:
            request = response.request
            kind = request.resource_type
            if kind == "document":
                frame = request.frame
                if frame == frame.page.main_frame:
                    return  # a navigation, the cohort's counter's own case
                kind = "subframe-document"
            elif kind not in SCRIPT_TYPES:
                return
            status = response.status
            product = 200 <= status < 300 and is_product_document(await response.text())
        except Exception as error:  # noqa: BLE001 - a lost reading is recorded, never raised
            self.errors.append(type(error).__name__)
            return
        self.events.append({"url": response.url, "status": status, "kind": kind,
                            "product_document": product})
        if product:
            self.fetched.add(identity)

    def record(self):
        return {"script_fetched": len(self.fetched), "script_fetched_urls": sorted(self.fetched),
                "script_events": self.events, "script_errors": self.errors,
                "definition": DEFINITION, "complete": not self.errors}


@contextmanager
def recording(adapter, candidate_urls):
    """For one trial, the adapter's browser with the extra listener on its context."""
    fetches = ScriptFetches(candidate_urls)
    original = adapter.research_browser

    @asynccontextmanager
    async def research_browser(config, recorder):
        async with original(config, recorder) as (context, cdp_url):
            pending = set()

            def on_response(response):
                task = asyncio.create_task(fetches.observe(response))
                pending.add(task)
                task.add_done_callback(pending.discard)

            context.on("response", on_response)
            try:
                yield context, cdp_url
            finally:
                # Before the original closes the context, so no reading is cut off.
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

    adapter.research_browser = research_browser
    try:
        yield fetches
    finally:
        adapter.research_browser = original
