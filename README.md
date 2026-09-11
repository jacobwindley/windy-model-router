# windy-model-router

A metadata-driven LLM routing proxy that sits in front of coding agents (opencode, pi.dev) and forwards `POST /v1/chat/completions` requests to a downstream [LiteLLM](https://github.com/BerriAI/litellm) (or bifrost) instance, rewriting the `model` field based on request shape.

Routing decisions are based only on request metadata — token count, tool count, multimodality, etc. — never on prompt content.

## Status

Early development. The proxy currently does pure pass-through: it forwards whatever model was requested, unchanged. The routing engine, model registry, and stats endpoints are not yet implemented.

Planned routing tiers:

1. **Tier 1** — rule-based, first-match-wins, driven by a config file (e.g. `config/rules.yaml`)
2. **Tier 2** — weighted scoring
3. **Tier 3** — UCB1 multi-armed bandit

## Setup

```bash
uv sync
cp .env.example .env   # then edit as needed
uv run uvicorn router.main:app --reload --port 8000
```

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

## API

- `POST /v1/chat/completions` — OpenAI-compatible chat completions endpoint; proxied to `LITELLM_URL`
- `GET /health` — health check
- `GET /admin/models` — model registry (not yet implemented)
- `GET /admin/stats` — routing stats (not yet implemented)

## Development

```bash
uv run pytest                                 # run tests
uv run pytest path/to/test_file.py::test_name # run a single test
uv add <package>                              # add a runtime dependency
uv add --dev <package>                        # add a dev dependency
```
