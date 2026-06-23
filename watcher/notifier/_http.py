"""Minimal HTTP POST helpers (stdlib only) used by webhook-style notifiers.

Kept in one place so tests can monkeypatch ``post_json`` / ``post_form`` to
capture calls without making real network requests.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .base import NotifierError

# Some providers (Discord/Cloudflare) reject the default "Python-urllib/x.y"
# User-Agent with HTTP 403 (Cloudflare error 1010). Always send a real one.
_USER_AGENT = "web3-contest-watcher/1.0 (+https://github.com/web3-contest-watcher)"


def _request(url: str, data: bytes, headers: dict, timeout: int) -> None:
    headers.setdefault("User-Agent", _USER_AGENT)
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 300:
                raise NotifierError(f"POST {url} returned HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300] if exc.fp else ""
        raise NotifierError(f"POST {url} failed: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise NotifierError(f"POST {url} failed: {exc.reason}") from exc


def post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 30) -> None:
    data = json.dumps(payload).encode("utf-8")
    final_headers = {"Content-Type": "application/json"}
    final_headers.update(headers or {})
    _request(url, data, final_headers, timeout)


def post_form(url: str, fields: dict, headers: dict | None = None, timeout: int = 30) -> None:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    final_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    final_headers.update(headers or {})
    _request(url, data, final_headers, timeout)
