"""Channel selection, fan-out, plugin loading, and payload shapes.

All HTTP is monkeypatched — no real network calls are made.
"""

from __future__ import annotations

import pytest

from watcher.config import Config
from watcher.notifier import (
    ConsoleNotifier,
    MultiNotifier,
    NotifierError,
    build_notifier,
)
from watcher.notifier import _http


@pytest.fixture
def capture_http(monkeypatch):
    calls = []
    monkeypatch.setattr(_http, "post_json",
                        lambda url, payload, headers=None, timeout=30:
                        calls.append(("json", url, payload, headers)))
    monkeypatch.setattr(_http, "post_form",
                        lambda url, fields, headers=None, timeout=30:
                        calls.append(("form", url, fields, headers)))
    return calls


def test_smtp_multi_recipient(monkeypatch):
    import smtplib
    from watcher.notifier.email_smtp import SmtpNotifier

    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=30):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            captured["login"] = (u, p)

        def send_message(self, msg, from_addr=None, to_addrs=None):
            captured["to_header"] = msg["To"]
            captured["to_addrs"] = to_addrs

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    SmtpNotifier("smtp.x", 465, "me@x.com", "pw", "a@x.com, b@y.com ,c@z.com").send("S", "B")
    # Recipients hidden from each other: placeholder To, delivery via envelope.
    assert captured["to_header"] == "undisclosed-recipients:;"
    assert captured["to_addrs"] == ["a@x.com", "b@y.com", "c@z.com"]  # trimmed
    assert captured["login"] == ("me@x.com", "pw")


def test_smtp_single_recipient_visible_to(monkeypatch):
    import smtplib
    from watcher.notifier.email_smtp import SmtpNotifier
    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=30):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            pass

        def send_message(self, msg, from_addr=None, to_addrs=None):
            captured["to_header"] = msg["To"]
            captured["to_addrs"] = to_addrs

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    SmtpNotifier("smtp.x", 465, "me@x.com", "pw", "solo@x.com").send("S", "B")
    assert captured["to_header"] == "solo@x.com"          # single recipient: shown
    assert captured["to_addrs"] == ["solo@x.com"]


def test_smtp_no_recipient_raises(monkeypatch):
    from watcher.notifier.email_smtp import SmtpNotifier
    with pytest.raises(NotifierError):
        SmtpNotifier("smtp.x", 465, "me@x.com", "pw", "   ").send("S", "B")


def cfg(notifier: str, dry_run: bool = False) -> Config:
    return Config(db_path=":memory:", source_url="x", sources="dailywarden",
                  discord_bot_token="", discord_channel_ids="",
                  recipient="me@example.com", notifier=notifier,
                  dry_run=dry_run, t24h_seconds=86400)


# ---- channel payloads ----------------------------------------------------
def test_discord_payload(capture_http, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/wh")
    build_notifier(cfg("discord")).send("Subj", "Body")
    kind, url, payload, _ = capture_http[0]
    assert kind == "json" and url == "https://discord.test/wh"
    assert "Subj" in payload["content"] and "Body" in payload["content"]


def test_slack_payload(capture_http, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    build_notifier(cfg("slack")).send("S", "B")
    _, url, payload, _ = capture_http[0]
    assert url == "https://hooks.slack.test/x" and "text" in payload


def test_telegram_payload(capture_http, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    build_notifier(cfg("telegram")).send("S", "B")
    _, url, payload, _ = capture_http[0]
    assert "bot123:abc/sendMessage" in url
    assert payload["chat_id"] == "999" and "text" in payload


def test_webhook_payload_with_auth(capture_http, monkeypatch):
    monkeypatch.setenv("WEBHOOK_URL", "https://my.test/hook")
    monkeypatch.setenv("WEBHOOK_TOKEN", "secret")
    build_notifier(cfg("webhook")).send("S", "B")
    _, url, payload, headers = capture_http[0]
    assert payload["subject"] == "S" and payload["body"] == "B" and "text" in payload
    assert headers["Authorization"] == "Bearer secret"


# ---- misconfiguration ----------------------------------------------------
def test_missing_config_raises(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    with pytest.raises(NotifierError):
        build_notifier(cfg("discord")).send("S", "B")


# ---- selection / fan-out / plugins --------------------------------------
def test_dry_run_forces_console():
    assert isinstance(build_notifier(cfg("discord", dry_run=True)), ConsoleNotifier)


def test_comma_list_builds_multinotifier(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/wh")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    n = build_notifier(cfg("discord,slack"))
    assert isinstance(n, MultiNotifier) and len(n.notifiers) == 2


def test_single_channel_not_wrapped(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/wh")
    assert not isinstance(build_notifier(cfg("discord")), MultiNotifier)


def test_custom_plugin_via_module_class():
    # Load a known no-arg Notifier through the module:Class plugin path.
    n = build_notifier(cfg("watcher.notifier.console:ConsoleNotifier"))
    assert isinstance(n, ConsoleNotifier)


def test_unknown_notifier_raises():
    with pytest.raises(NotifierError):
        build_notifier(cfg("carrier-pigeon"))


# ---- MultiNotifier delivery semantics -----------------------------------
class _Ok:
    def __init__(self): self.sent = 0
    def send(self, s, b): self.sent += 1


class _Fail:
    def send(self, s, b): raise RuntimeError("down")


def test_multi_succeeds_if_one_channel_works():
    ok = _Ok()
    MultiNotifier([ok, _Fail()]).send("S", "B")  # must NOT raise
    assert ok.sent == 1


def test_multi_raises_if_all_fail():
    with pytest.raises(NotifierError):
        MultiNotifier([_Fail(), _Fail()]).send("S", "B")
