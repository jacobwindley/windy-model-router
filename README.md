# windy-model-router

A metadata-driven LLM routing proxy that sits in front of coding agents (opencode, pi.dev) and forwards `POST /v1/chat/completions` requests to a downstream [LiteLLM](https://github.com/BerriAI/litellm) (or bifrost) instance, rewriting the `model` field based on request shape.

Routing decisions are based only on request metadata — token count, tool count, multimodality, etc. — never on prompt content.

It also includes a **session advisor**: a Claude Code status line that recommends when to compact or clear context and when to switch models. It is the first step toward a cross-agent harness that can optionally apply those swaps itself (see [`TODO.md`](TODO.md)).

## Status

Early development. Model registry and stats endpoints are not yet implemented.

Session advisor: advise-only Claude Code status line — **implemented**. Hooks, autopilot, and Codex/opencode support are planned.

Routing tiers:

1. **Tier 1** — rule-based, first-match-wins, driven by `config/rules.yaml` — **implemented**
2. **Tier 2** — weighted scoring — not yet implemented
3. **Tier 3** — UCB1 multi-armed bandit — not yet implemented

Each response carries the routing decision in an `X-Route-Info` response header (JSON: matched tier, rule id, reason, extracted metadata) — kept out of the response body so it stays OpenAI-compatible for real clients.

## Setup

```bash
uv sync
cp .env.example .env   # then edit as needed
uv run uvicorn router.main:app --reload --port 8000
```

For local testing/iteration without a real LiteLLM deployment or provider API keys, see the sibling [`litellm-local`](../litellm-local) project — a local LiteLLM proxy backed by Ollama, exposing `fast-model`/`balanced-model`/`smart-model` aliases that `config/rules.yaml` routes to.

### Routing demo UI

A small [Dash](https://dash.plotly.com/) app that sends chat messages to the router and visualizes which Tier-1 rule fired and why:

```bash
uv sync --extra ui
uv run python ui/app.py
```

Open `http://localhost:8050`. It's a separate process/port (:8050) from the router — it talks to the router over HTTP like any other client.

## Session advisor (Claude Code status line)

A status-line command that watches your Claude Code session and shows advice under the prompt:

```
Opus 5.5 · ctx 92% · cache warm 4m · ⚠ context 92% full — run /compact or /clear
```

It is advise-only: it tells you which command to run and changes nothing itself. It reads only the session metadata Claude Code passes to the status line, never prompt content. It doesn't need the router to be running.

### Install

1. Run `uv sync` in this repo.
2. Add this to `~/.claude/settings.json` (adjust the path):

```json
"statusLine": {
  "type": "command",
  "command": "uv run --project C:/path/to/windy-model-router windy-statusline"
}
```

It works with both claude.ai subscriptions and API keys. It detects which one you use from whether Claude Code sends rate-limit data, which it does only for subscribers.

### Rules

Rules live in `config/advisor.yaml`. To use a different file, set the `WINDY_ADVISOR_CONFIG` environment variable. Unlike `rules.yaml`, every matching rule fires, and the status line shows the most severe one.

| Rule | Fires when | Suggests |
|---|---|---|
| `context-critical` | context ≥ 90% full | `/compact` or `/clear` |
| `context-high` | context ≥ 70% full | `/compact` |
| `context-large` | context ≥ 300k tokens (percent thresholds are lenient on 1M-context models) | `/compact` |
| `rate-limit-pressure` | subscription, a rate-limit window ≥ 75% used | next cheaper model (`opus → sonnet → haiku`) |
| `session-cost` | API key, session cost ≥ $5 | next cheaper model |

When the prompt cache is warm, model-switch advice includes what switching would cost: Claude Code reports exactly how many tokens a cache miss re-sends, e.g. "switching now re-sends ~100k tokens uncached; cache cools in 4m."

To save the raw payload Claude Code sends, add `--capture <path>` to the command. This is how the test fixture was made.

See [`TODO.md`](TODO.md) for what's next: hooks, an autopilot toggle that swaps models itself, the router as an Anthropic `/v1/messages` gateway, and Codex/opencode adapters.

## Configuration

Set via `.env` (see `.env.example`):

| Variable | Description |
|---|---|
| `LITELLM_URL` | URL of your LiteLLM or bifrost instance |
| `ROUTER_API_KEY` | API key required to authenticate requests to this router (leave empty to disable auth) |
| `LITELLM_API_KEY` | API key passed through to LiteLLM, if it requires one |
| `SESSION_TTL_SECONDS` | Session state TTL |
| `SESSION_MAX_SIZE` | Max session state cache size |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `RULES_PATH` | Path to the Tier-1 routing rules file (default `config/rules.yaml`) |

## API

- `POST /v1/chat/completions` — OpenAI-compatible chat completions endpoint; proxied to `LITELLM_URL`
- `GET /health` — health check
- `GET /admin/models` — model registry (not yet implemented)
- `GET /admin/stats` — routing stats (not yet implemented)

## Development

```bash
uv sync --extra dev                           # install test dependencies (not installed by bare `uv sync`)
uv run pytest                                 # run tests
uv run pytest path/to/test_file.py::test_name # run a single test
uv add <package>                              # add a runtime dependency
uv add --dev <package>                        # add a dev dependency
```
