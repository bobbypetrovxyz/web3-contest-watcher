# Web3 Contest & Bug-Bounty Watcher

Monitors web3 security **contests and bug bounties** and notifies you:

1. **`new`** — when a contest/bounty is first listed, and
2. **`t24h`** — within ~24 hours before a contest starts (contests only).

It reads from **multiple pluggable sources** (an aggregator plus direct
platform feeds), runs as a one-shot command on a schedule, and delivers alerts
to **pluggable notification channels**. The runtime has **no third-party
dependencies** (Python stdlib only).

## Sources

Choose which sources to poll with `WATCHER_SOURCES` (comma-separated):

| Name | Provides | Data access | Alerts |
|------|----------|-------------|--------|
| `dailywarden` | aggregated contests (Code4rena, Sherlock, Cantina, HackenProof, Immunefi, …) | embedded JSON | `new` + `t24h` |
| `sherlock` | Sherlock audit contests | public JSON API | `new` + `t24h` |
| `immunefi` | Immunefi bug bounties (perpetual) **and** audit competitions (time-boxed) | parsed from page | bounties `new`; competitions `new` + `t24h` |
| `cantina` | Cantina bounties (perpetual) **and** competitions (time-boxed) | parsed from page | bounties `new`; competitions `new` + `t24h` |
| `sch` | aggregated contests & bounties (Code4rena, Sherlock, CodeHawks, Cantina, Immunefi, HackenProof) | parsed from page | `new` (+ `t24h` for contests) |
| `discord` | announcements you've Followed into your own Discord server | Discord bot (REST) | `new` (relay) |

```bash
WATCHER_SOURCES=dailywarden,sherlock,immunefi,cantina,sch,discord   # default: dailywarden
```

To avoid duplicate alerts, `sch` skips Sherlock/Cantina/Immunefi (covered by
direct sources) and emits the rest with canonical platform URLs, so HackenProof
contests dedup against `dailywarden`. It's how we reach HackenProof (otherwise
Cloudflare-gated) and its bug bounties.

Each listing is a **contest** (time-boxed — eligible for `t24h`), a **bounty**
(perpetual — `new` only), or an **announcement** (Discord relay — `new` only);
alerts are labelled accordingly (`[New Contest]` / `[New Bounty]` /
`[New Announcement]`). The `immunefi` source returns both its perpetual bounties
and its time-boxed competitions, distinguished by this label.

**Failure isolation:** sources are fetched independently. One broken source
never silences the others — you get a throttled warning naming it while alerts
from the working sources still go out.

**Per-source seeding:** the first time a source is seen (first run, or a source
you enable later) its current listings are recorded silently, so enabling a new
source never floods you with hundreds of "new" alerts for things that already
existed.

Adding a source = one small adapter implementing `fetch() -> list[Contest]`
(see [CONTRIBUTING.md](CONTRIBUTING.md)).

### Discord source setup (optional)

The `discord` source relays announcements that platforms post in their Discord
servers — useful as a catch-all, since announcements often precede the API
listing. Discord bots can only read servers they're added to, so you aggregate
others' announcements into a server **you** control using Discord's **Follow**
feature, then point a read-only bot at it. One-time setup:

1. **Create a server** you control (or reuse one).
2. **Follow platform announcement channels into it:** join each platform's
   Discord, open its 📢 **Announcement** channel, click **Follow**, and pick a
   channel in your server. (Only 📢 Announcement channels are followable.)
3. **Create a bot:** Discord Developer Portal → New Application → **Bot** →
   enable **Message Content Intent**. Copy the **bot token**.
4. **Add the bot to your server:** OAuth2 → URL Generator → scope `bot`,
   permissions **View Channels** + **Read Message History** → open the URL,
   authorize.
5. **Get the channel ID(s):** enable Developer Mode, right-click the channel(s)
   → Copy Channel ID.
6. Set `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_IDS` (comma-separated) in `.env`,
   add `discord` to `WATCHER_SOURCES`.

Each deployer runs their **own** bot + server — the bot token is a per-user
secret (like the others), never shared. Relay mode emits one `new` alert per
announcement (no `t24h`, since free-form announcements have no reliable start
time).

## Notification channels

Pick one or several with `WATCHER_NOTIFIER` (comma-separated to fan out):

| Name | Delivers via | Required env |
|------|--------------|--------------|
| `console` | stdout (default) | — |
| `smtp` / `gmail` | email | `WATCHER_RECIPIENT`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` |
| `discord` | webhook | `DISCORD_WEBHOOK_URL` |
| `slack` | webhook | `SLACK_WEBHOOK_URL` |
| `telegram` | Bot API | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| `webhook` | generic JSON POST | `WEBHOOK_URL` (+ optional `WEBHOOK_TOKEN`) |

**Custom channel, no fork:** set `WATCHER_NOTIFIER=your_pkg.module:YourNotifier`
to a class with `send(self, subject, body)`. It's instantiated with no args and
reads its own env — so a channel needing a heavy SDK lives in *your* package
while the core stays dependency-free.

See [`.env.example`](.env.example) for every variable.

## Install

**pipx (recommended — global `web3-watch` command):**
```bash
pipx install git+https://github.com/bobbypetrovxyz/web3-contest-watcher
```

**From source (stdlib only):**
```bash
git clone https://github.com/bobbypetrovxyz/web3-contest-watcher
cd web3-contest-watcher
# optional: pip install -e ".[dev]"   # for tests
```

**Docker:**
```bash
docker build -t web3-watch .
docker run --env-file .env -v "$PWD/data:/data" web3-watch --seed
```

## Configure & run

```bash
cp .env.example .env        # choose channel(s) + fill secrets

# Preview what WOULD be sent (no send, no state written):
WATCHER_DRY_RUN=1 web3-watch          # or: python3 -m watcher.run

# Just run it. The first run (per source) records existing listings silently,
# so you won't be flooded — no explicit seeding step is required:
web3-watch

# Subsequent runs alert on genuinely new / soon-to-start contests:
web3-watch
```

`--seed` is still available to force-record everything silently (e.g. to
re-baseline), but is optional thanks to per-source seeding.

(If you installed from source without the entry point, use
`python3 -m watcher.run` in place of `web3-watch`.)

## Scheduling

Run it 3×/day. State lives in SQLite and the `notifications(contest_id,
alert_type)` key guarantees each alert fires at most once, so cadence and alert
logic are independent.

**Linux/WSL cron:**
```bash
sudo service cron start     # WSL only: cron isn't auto-started
crontab -e
# 0 */8 * * * web3-watch >> ~/web3-watch.log 2>&1
```
**WSL caveat:** WSL sleeps with Windows, so runs can be missed → late/skipped
alerts. At an 8h cadence the `t24h` alert already lands 16–24h before start
(worst case). For reliable timing, use an always-on host (see `Dockerfile`).

## Failure handling

Sources are fetched independently:
- **Some sources fail** → alerts from the working ones still go out, plus one
  throttled **warning** naming the failing source(s).
- **All sources fail** (or all return zero listings) → one **failure alert**
  ("parser may be stale"), and the process exits non-zero.

All failure/warning messages are throttled to once per ~24h (per source) to
avoid spam. There is no LLM fallback in V1.

## Develop / test

```bash
pip install -e ".[dev]"
pytest -q
```
Covers fixture parsing, the alert/idempotency/seed/dry-run logic (injected
clock), and every channel's payload (monkeypatched HTTP — no real sends).
See [CONTRIBUTING.md](CONTRIBUTING.md) to add a channel or a contest source.

## Architecture

A deterministic core with two plugin seams, fanned out over many instances:
- **`Source`** (`watcher/sources/base.py`) — `fetch() -> list[Contest]`;
  selected via `WATCHER_SOURCES`, fetched with per-source failure isolation.
- **`Notifier`** (`watcher/notifier/base.py`) — `send(subject, body)`;
  selected via `WATCHER_NOTIFIER`, fan-out via comma list.

No LLM sits on the alert hot path. Roadmap (V2): LLM enrichment of the Discord
relay into structured records, self-discovery of new sites, and an optional MCP
server wrapping these interfaces once an agent orchestrates them. (HackenProof —
Cloudflare-gated for direct scraping — is now covered via the `sch` aggregator.)

## License

[MIT](LICENSE)
