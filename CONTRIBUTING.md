# Contributing

Thanks for helping improve the Web3 Contest & Bug-Bounty Watcher!

## Dev setup

```bash
git clone https://github.com/bobbypetrovxyz/web3-contest-watcher
cd web3-contest-watcher
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

The runtime is standard-library only. Please keep it that way — if a feature
needs a third-party package, prefer adding it as an **optional extra** or a
custom plugin rather than a hard runtime dependency.

## Adding a notification channel

1. Create `watcher/notifier/<name>.py` with a class implementing
   `send(self, subject: str, body: str) -> None`. Use `watcher.notifier._http`
   for HTTP and `watcher.notifier._format.chat_text` to format chat messages.
   Raise `NotifierError` on misconfiguration.
2. Register it in `watcher/notifier/__init__.py`: add the name to `_BUILTINS`
   and a branch in `_build_one` that reads its env vars.
3. Document its env vars in `.env.example` and the README channel table.
4. Add a payload test in `tests/test_notifiers.py` (monkeypatch `_http`).

Don't want it in core? Ship your own class and point users at it with
`WATCHER_NOTIFIER=your_pkg.module:YourNotifier` — no fork required.

## Adding a contest / bounty source

1. Create `watcher/sources/<name>.py` with a class exposing `name` and
   `fetch(self) -> list[Contest]`. Raise `SourceError` if the remote data is
   missing or its structure changed. Keep parsing in a module-level
   `parse_*(...)` function so it can be unit-tested without network.
2. Normalize timestamps to **epoch seconds UTC** (`models.ms_to_s` helps for
   millisecond inputs). Give each record a **source-namespaced id**
   (e.g. `f"<name>:{remote_id}"`) so ids never collide across sources.
3. Set `source="<name>"` and `kind`: `"contest"` for time-boxed entries (with a
   `start_ts`, eligible for `t24h`) or `"bounty"` for perpetual ones
   (`start_ts=None`, `new`-only).
4. Register it in `watcher/sources/__init__.py`: add a branch in `build_sources`
   that instantiates it for its name.
5. Document the name in `.env.example`'s `WATCHER_SOURCES` list and the README
   Sources table.
6. Add a parser test against a saved fixture in `fixtures/`.

## Guidelines

- Run `pytest -q` before opening a PR; CI runs on 3.10–3.12.
- Keep alert logic deterministic and testable (inject `now`, monkeypatch HTTP).
- Never commit secrets. `.env` is gitignored — document new vars in
  `.env.example` with placeholder values only.
