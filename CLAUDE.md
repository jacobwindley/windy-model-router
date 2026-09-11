# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`windy-model-router` is a metadata-driven LLM routing proxy that sits in front of coding agents (opencode, pi.dev) and forwards `POST /v1/chat/completions` requests to a downstream LiteLLM (or bifrost) instance, rewriting the `model` field based on request shape. It intentionally does **not** inspect prompt content for routing decisions — only request metadata (token count, tool count, multimodality, etc.).

The project is in early, incremental development. Tier 1 (rule-based, first-match-wins) routing is implemented; the model registry and stats endpoints are still stubbed out (`router/main.py`'s `/admin/stats` and `/admin/models`).

## Commands

This project uses `uv` (see global Python package management rules — always `uv`, never `pip`).

```bash
uv sync                      # install/sync dependencies
uv run uvicorn router.main:app --reload --port 8000   # run the dev server
uv run pytest                # run tests (pytest-asyncio, mode=auto — no @pytest.mark.asyncio needed)
uv run pytest path/to/test_file.py::test_name   # run a single test
uv add <package>              # add a runtime dependency
uv add --dev <package>        # add a dev dependency
uv sync --extra dev --extra ui   # install test + demo-UI dependencies
uv run python ui/app.py      # run the Dash routing-demo UI (:8050) — separate process, needs the router running
```

No lint/format tooling is configured in `pyproject.toml`. `dev` (pytest) and `ui` (dash) are optional-dependency groups, not installed by a bare `uv sync` — the core router has neither as a hard dependency.

Configuration is via `.env` (see `.env.example` for the full list — `LITELLM_URL`, `ROUTER_API_KEY`, `LITELLM_API_KEY`, `SESSION_TTL_SECONDS`, `SESSION_MAX_SIZE`, `LOG_LEVEL`, `RULES_PATH`), loaded through `router/config.py`'s pydantic-settings `Settings`.

For local testing without a real LiteLLM deployment, see the sibling `litellm-local` project (`../litellm-local`) — a LiteLLM proxy backed by a local Ollama model, exposing `fast-model`/`balanced-model`/`smart-model` aliases that this repo's `config/rules.yaml` routes to.

## Architecture

Request flow: `POST /v1/chat/completions` (`router/main.py`) → optional bearer-token auth check against `ROUTER_API_KEY` → `handle_chat_completion` (`router/proxy/handler.py`) → extract metadata → evaluate Tier-1 rules → rewrite `model` → `forward` (`router/proxy/forwarder.py`) → downstream LiteLLM/bifrost at `LITELLM_URL`. The routing decision is also attached to the response as a JSON-encoded `X-Route-Info` header (not the response body, to keep it OpenAI-compatible for real clients).

- **`router/config.py`** — single `Settings` object (pydantic-settings) loaded from `.env`, imported everywhere as `from router.config import settings`.
- **`router/proxy/types.py`** — request/response Pydantic models. `ChatCompletionRequest`/`Message`/`ContentPart` mirror the OpenAI chat completions schema with `extra = "allow"` so unknown fields pass through untouched. `RouteInfo` (`original_model`, `routed_model`, `rule_id`, `reason`, `token_count`) is the shape a routing decision produces.
- **`router/proxy/metadata.py`** — the only module that touches raw message content. `extract_metadata()` derives a `RequestMetadata` (token count via a fixed `tiktoken` `cl100k_base` encoding — a size estimate, not billing-accurate; message/tool counts; multimodal flag). Everything downstream consumes only this, never raw text.
- **`router/proxy/rules.py`** — Tier-1 rules engine. Loads `config/rules.yaml` (path from `settings.rules_path`) into `Rule`/`RuleMatch` models with `extra: "forbid"` (a typo'd condition key fails loudly), validates exactly one `default: true` catch-all rule exists, is last, and always matches. `get_rules()` is `lru_cache`d and called once from `main.py`'s `lifespan`, so a broken rules file fails app **startup**, not the first request — editing `rules.yaml` needs a restart, no hot-reload. `evaluate_rules()` is first-match-wins.
- **`router/proxy/route_info.py`** — builds the `X-Route-Info` header payload (matched tier, decision, metadata, a static Tier 1/2/3 status descriptor — Tiers 2/3 are hardcoded `"not_implemented"`, no scaffolding for them yet). `encode_route_info_header()` must keep `ensure_ascii=True`: Starlette encodes header values as latin-1 and a non-ASCII `reason` string would crash the request otherwise.
- **`router/proxy/handler.py`** — orchestrates one request: parse body, `extract_metadata` → `evaluate_rules` → `forward` with the routed model → attach the `X-Route-Info` header → log a structured `"routed"` event.
- **`router/proxy/forwarder.py`** — owns the single shared `httpx.AsyncClient` (300s timeout, lazily created/recreated if closed) and does the actual upstream call, branching on `body["stream"]` into buffered (`_complete`) vs. SSE passthrough (`_stream`) responses. Strips `host`/`content-length`/`transfer-encoding` from forwarded headers and swaps in `LITELLM_API_KEY` as the upstream bearer token when set. Setting headers on its returned `Response`/`StreamingResponse` after the fact (as `handler.py` does for `X-Route-Info`) is safe for both paths — headers are finalized before any body is sent.
- Logging is `structlog` configured in `router/main.py`'s module scope from `LOG_LEVEL`, with the level applied via `structlog.make_filtering_bound_logger`.

### `ui/app.py` — Dash routing-demo UI

A standalone Dash app (own process, `:8050`), not served by the router — it's an HTTP client like any other, calling `POST /v1/chat/completions` on the router and rendering the decision from the `X-Route-Info` header as a Plotly tier-pipeline diagram (Tier 1 highlighted with the matched rule/reason, Tiers 2/3 shown as not-yet-implemented). Colors are pulled from the project's `dataviz` skill palette (status colors for matched/pending, not picked ad hoc). Demo checkboxes ("include a tool call", "include image content", "pad prompt over 8000 tokens") construct requests that deliberately trigger each Tier-1 rule. A tool-call response has `content: null` with `tool_calls` populated instead — the UI must render that case, not just assume `message.content` is always a string. `dash` is an optional dependency (`[project.optional-dependencies].ui`) kept out of the core router's install.

### Tiers 2/3

Not implemented. `router/proxy/route_info.py`'s `TIERS` tuple and `MATCHED_TIER = 1` are the only place they're referenced (as static "not_implemented" descriptors) — don't assume any weighted-scoring or bandit logic exists elsewhere. `SESSION_TTL_SECONDS`/`SESSION_MAX_SIZE` in settings anticipate a future session-state cache (e.g. for bandit state) that doesn't exist in code yet. `/admin/models` and `/admin/stats` are still placeholder responses.
