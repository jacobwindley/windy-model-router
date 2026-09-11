# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`windy-model-router` is a metadata-driven LLM routing proxy that sits in front of coding agents (opencode, pi.dev) and forwards `POST /v1/chat/completions` requests to a downstream LiteLLM (or bifrost) instance, rewriting the `model` field based on request shape. It intentionally does **not** inspect prompt content for routing decisions — only request metadata (token count, tool count, multimodality, etc.).

The project is in early, incremental development. `router/proxy/handler.py` currently does pure pass-through (Phase 1) — it forwards whatever model was requested unchanged. The routing engine, model registry, and stats endpoints are stubbed out (`router/main.py`'s `/admin/stats` and `/admin/models`) and not yet implemented.

## Commands

This project uses `uv` (see global Python package management rules — always `uv`, never `pip`).

```bash
uv sync                      # install/sync dependencies
uv run uvicorn router.main:app --reload --port 8000   # run the dev server
uv run pytest                # run tests (pytest-asyncio, mode=auto — no @pytest.mark.asyncio needed)
uv run pytest path/to/test_file.py::test_name   # run a single test
uv add <package>              # add a runtime dependency
uv add --dev <package>        # add a dev dependency
```

There is no test suite yet, and no lint/format tooling configured in `pyproject.toml`.

Configuration is via `.env` (see `.env.example` for the full list — `LITELLM_URL`, `ROUTER_API_KEY`, `LITELLM_API_KEY`, `SESSION_TTL_SECONDS`, `SESSION_MAX_SIZE`, `LOG_LEVEL`), loaded through `router/config.py`'s pydantic-settings `Settings`.

## Architecture

Request flow: `POST /v1/chat/completions` (`router/main.py`) → optional bearer-token auth check against `ROUTER_API_KEY` → `handle_chat_completion` (`router/proxy/handler.py`) → (future: extract metadata → routing engine → rewrite `model`) → `forward` (`router/proxy/forwarder.py`) → downstream LiteLLM/bifrost at `LITELLM_URL`.

- **`router/config.py`** — single `Settings` object (pydantic-settings) loaded from `.env`, imported everywhere as `from router.config import settings`.
- **`router/proxy/types.py`** — request/response Pydantic models. `ChatCompletionRequest`/`Message`/`ContentPart` mirror the OpenAI chat completions schema with `extra = "allow"` so unknown fields pass through untouched. `RouteInfo` is the shape a routing decision will eventually produce (`original_model`, `routed_model`, `rule_id`, `reason`, `token_count`) — not yet wired up anywhere.
- **`router/proxy/handler.py`** — orchestrates one request: parse body into `ChatCompletionRequest`, decide `routed_model` (currently passthrough), call `forward`, log a structured `"routed"` event with latency and status.
- **`router/proxy/forwarder.py`** — owns the single shared `httpx.AsyncClient` (300s timeout, lazily created/recreated if closed) and does the actual upstream call, branching on `body["stream"]` into buffered (`_complete`) vs. SSE passthrough (`_stream`) responses. Strips `host`/`content-length`/`transfer-encoding` from forwarded headers and swaps in `LITELLM_API_KEY` as the upstream bearer token when set.
- Logging is `structlog` configured in `router/main.py`'s module scope from `LOG_LEVEL`, with the level applied via `structlog.make_filtering_bound_logger`.

### Planned routing design (not yet implemented, but shapes the intended structure)

- Routing decisions must only ever consume derived request metadata (token count via `tiktoken`, message/tool counts, multimodal flags) — never raw prompt text — so keep any future metadata-extraction step and routing-decision step cleanly separated from each other.
- Routing tiers, in intended build order: **Tier 1** rule-based, first-match-wins, driven by a config file (e.g. `config/rules.yaml`, not yet created); **Tier 2** weighted scoring; **Tier 3** a UCB1 multi-armed bandit. Expect these to land incrementally — don't assume later tiers exist.
- `SESSION_TTL_SECONDS`/`SESSION_MAX_SIZE` in settings anticipate a session-state cache (e.g. for sticky routing or bandit state) that doesn't exist in code yet.
- `/admin/models` is meant to eventually expose the model registry; `/admin/stats` is meant to expose routing stats — both are placeholder responses today.
