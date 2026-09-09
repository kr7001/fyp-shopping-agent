"""Thin Magento 2 REST client, enough to author catalogue fixtures.

Only the handful of endpoints the seeder needs. Everything returns parsed JSON
and raises MagentoError on a non-2xx, so callers do not have to check status.
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field
from typing import Any

import requests

DEFAULT_BASE_URL = "http://localhost:7770"


class MagentoError(RuntimeError):
    """A Magento REST call came back non-2xx."""

    def __init__(self, method: str, path: str, status: int, body: str) -> None:
        super().__init__(f"{method} {path} -> HTTP {status}: {body[:400]}")
        self.status = status
        self.body = body


class NotFound(MagentoError):
    """The requested entity does not exist. Raised instead of MagentoError on 404."""


@dataclass
class Magento:
    """Authenticated session against one Magento instance.

    The admin token is fetched lazily on first use and reused. Magento's tokens
    last four hours, which outlives any seeding run, so there is no refresh path.
    """

    base_url: str = DEFAULT_BASE_URL
    username: str = "admin"
    password: str = "admin1234"
    timeout: int = 180

    _session: requests.Session = field(default_factory=requests.Session, repr=False)
    _token: str | None = field(default=None, repr=False)

    # ---------------------------------------------------------------- transport

    @property
    def token(self) -> str:
        if self._token is None:
            url = f"{self.base_url}/rest/V1/integration/admin/token"
            response = self._session.post(
                url,
                json={"username": self.username, "password": self.password},
                timeout=self.timeout,
            )
            if response.status_code != 200:
                raise MagentoError("POST", "/integration/admin/token",
                                   response.status_code, response.text)
            self._token = response.json()
        return self._token

    def call(self, method: str, path: str, payload: Any = None) -> Any:
        """Issue one REST call. `path` is relative to /rest/V1."""
        url = f"{self.base_url}/rest/V1{path}"
        response = self._session.request(
            method,
            url,
            json=payload,
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"},
            timeout=self.timeout,
        )
        if response.status_code == 404:
            raise NotFound(method, path, 404, response.text)
        if not response.ok:
            raise MagentoError(method, path, response.status_code, response.text)
        return response.json() if response.content else None

    def get(self, path: str) -> Any:
        return self.call("GET", path)

    def post(self, path: str, payload: Any) -> Any:
        return self.call("POST", path, payload)

    def put(self, path: str, payload: Any) -> Any:
        return self.call("PUT", path, payload)

    def delete(self, path: str) -> Any:
        return self.call("DELETE", path)

    # ------------------------------------------------------------------ helpers

    def exists(self, path: str) -> bool:
        """True if a GET on `path` finds something. Used for idempotency checks."""
        try:
            self.get(path)
        except NotFound:
            return False
        return True

    # ------------------------------------------------------------- catalogue API

    def attribute(self, code: str) -> dict | None:
        try:
            return self.get(f"/products/attributes/{code}")
        except NotFound:
            return None

    def product(self, sku: str) -> dict | None:
        try:
            return self.get(f"/products/{urllib.parse.quote(sku, safe='')}")
        except NotFound:
            return None

    def delete_product(self, sku: str) -> bool:
        try:
            self.delete(f"/products/{urllib.parse.quote(sku, safe='')}")
        except NotFound:
            return False
        return True

    def attribute_set_groups(self, set_id: int) -> list[dict]:
        query = urllib.parse.urlencode({
            "searchCriteria[filterGroups][0][filters][0][field]": "attribute_set_id",
            "searchCriteria[filterGroups][0][filters][0][value]": set_id,
        })
        return self.get(f"/products/attribute-sets/groups/list?{query}")["items"]
