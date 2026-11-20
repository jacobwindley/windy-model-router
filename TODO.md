# TODO

Direction: grow the router into a harness that recommends (and optionally auto-applies)
model swaps and context management across coding agents. Phase 1 (`router/advisor/` +
Claude Code status line, advise-only) is done; everything below is deferred.

## Verify phase 1 against reality
- [x] Capture a real Claude Code status-line payload (redacted) as the test fixture
      (`windy-statusline --capture <path>` saves the raw stdin).
- [ ] Tune `config/advisor.yaml` thresholds from real use.
- [ ] Use more `prompt_cache` signals Claude Code already reports: `miss_causes` /
      `last_miss_cause` (e.g. `ttl_expired_1h`), `hit_ratio`, `expected_rebuilds` — e.g. advise
      "cache is about to expire; a pause now will re-send ~100k tokens".
- [ ] Rate-limit advice uses the max of `five_hour`/`seven_day`; consider window-specific
      messages using `resets_at` ("seven-day window 80% used, resets Tue").

## Claude Code hooks
- [ ] `PostToolUseFailure` counter → struggle signal → suggest *up*shifting (needs session state).
- [ ] `PreModelSwitch` hook: warn/ask when the prompt cache is warm (Claude Code already
      confirms in some cases — check overlap first).
- [ ] `PreCompact` hook: stdout steers the compaction summary.
- [ ] Find out whether `systemMessage` is shown to the user on `Stop` (only confirmed for `PostToolUse`).

## Session state
- [ ] Per-session store (failure counts, recommendation history) shared by hooks and the status line.
      Likely an HTTP advisor endpoint on the router, with the status line as a thin client that
      falls back to local evaluation if the router is down.
- [ ] Dash UI: session-timeline view of snapshots + recommendations.

## Router as an Anthropic gateway (prerequisite for autopilot in Claude Code)
- [ ] `POST /v1/messages` passthrough (Anthropic Messages format), pointed at via `ANTHROPIC_BASE_URL`.
      Forward `anthropic-version`, `anthropic-beta`, and `Authorization` (claude.ai subscription
      login) as well as `x-api-key` (API-key users). Support streaming.
- [ ] `GET /v1/models` so `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1` populates `/model`.

## Autopilot
- [ ] Per-session autopilot toggle (off = advise only).
- [ ] Rewrite `model` only at cache-cold boundaries (cache expired, right after /clear or /compact)
      unless a struggle signal justifies re-sending the context uncached.
- [ ] Status line shows mode + actually-routed model (Claude Code will still display the model it requested).

## Model registry & data
- [ ] Model registry (`/admin/models`): context windows, input/cached/output prices, capabilities.
- [ ] Per-harness model discovery (Claude Code aliases + `ANTHROPIC_DEFAULT_*_MODEL`, gateway discovery).
- [ ] Trace store (SQLite outcome log) and real `/admin/stats`.
- [ ] Tier 2 (weighted scoring) / Tier 3 (bandit) using recorded outcomes as reward signal.

## Other harnesses
- [ ] Research extension points for Codex and opencode (status line / plugin / hooks equivalents).
- [ ] Adapters mapping their session data to `SessionSnapshot`.
