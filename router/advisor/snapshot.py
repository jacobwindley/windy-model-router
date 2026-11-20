from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AuthMode = Literal["subscription", "api_key", "unknown"]


class SessionSnapshot(BaseModel):
    """Harness-agnostic view of one coding-agent session at a point in time.

    Every harness adapter (Claude Code, later Codex/opencode) maps its own data
    into this shape. Metadata only — never prompt or response content.
    """

    harness: str
    session_id: str | None = None
    model_id: str | None = None
    model_display_name: str | None = None

    context_used_pct: float | None = None
    context_window_size: int | None = None

    # Token usage of the most recent request — together they approximate the
    # prompt size that a model switch would re-send without cache.
    input_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None

    cache_warm: bool | None = None
    cache_expires_at: datetime | None = None
    # Exact tokens a cache miss would re-send, when the harness reports it
    # (Claude Code: prompt_cache.recache_tokens_if_cold). Preferred over the
    # prompt_tokens estimate.
    recache_tokens: int | None = None

    session_cost_usd: float | None = None
    rate_limit_pct: float | None = None  # highest used % across rate-limit windows
    auth_mode: AuthMode = "unknown"

    @property
    def prompt_tokens(self) -> int | None:
        parts = [self.input_tokens, self.cache_read_tokens, self.cache_creation_tokens]
        if all(p is None for p in parts):
            return None
        return sum(p or 0 for p in parts)
