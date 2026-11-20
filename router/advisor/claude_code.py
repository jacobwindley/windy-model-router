"""Claude Code adapter: a status-line command that shows advisor recommendations.

Claude Code pipes a JSON session payload to the status-line command on stdin and
renders its stdout under the prompt. Install via `statusLine` in
~/.claude/settings.json (see README).

Parsing is deliberately defensive — a missing or renamed field degrades to None,
and any failure falls back to a plain line, so the status line never breaks.
"""

import json
import sys
from datetime import datetime, timezone
from typing import Any

from router.advisor.engine import (
    Recommendation,
    cache_minutes_left,
    evaluate,
    get_advisor_config,
)
from router.advisor.snapshot import SessionSnapshot

ANSI = {
    "info": "\033[2m",  # dim
    "warn": "\033[33m",  # yellow
    "critical": "\033[31m",  # red
    "reset": "\033[0m",
}
SEVERITY_MARK = {"info": "·", "warn": "⚠", "critical": "⚠"}


def _get(d: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
    return d


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _int(v: Any) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None


def _datetime(v: Any) -> datetime | None:
    """Accept ISO-8601 strings or epoch seconds/milliseconds."""
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    n = _num(v)
    if n is None:
        return None
    if n > 1e12:  # milliseconds
        n /= 1000
    return datetime.fromtimestamp(n, tz=timezone.utc)


def _rate_limit_pct(rate_limits: Any) -> float | None:
    """Highest used-% across rate-limit windows (five_hour, seven_day, ...)."""
    if not isinstance(rate_limits, dict):
        return None
    pcts = []
    for window in rate_limits.values():
        if not isinstance(window, dict):
            continue
        for key in ("used_percentage", "utilization", "percent_used"):
            if (pct := _num(window.get(key))) is not None:
                pcts.append(pct)
                break
    return max(pcts) if pcts else None


def to_snapshot(payload: dict) -> SessionSnapshot:
    rate_limits = payload.get("rate_limits")
    usage = _get(payload, "context_window", "current_usage")
    return SessionSnapshot(
        harness="claude_code",
        session_id=payload.get("session_id"),
        model_id=_get(payload, "model", "id"),
        model_display_name=_get(payload, "model", "display_name"),
        context_used_pct=_num(_get(payload, "context_window", "used_percentage")),
        context_window_size=_int(_get(payload, "context_window", "context_window_size")),
        input_tokens=_int(_get(usage, "input_tokens")),
        cache_read_tokens=_int(_get(usage, "cache_read_input_tokens")),
        cache_creation_tokens=_int(_get(usage, "cache_creation_input_tokens")),
        cache_warm=w if isinstance(w := _get(payload, "prompt_cache", "warm"), bool) else None,
        cache_expires_at=_datetime(_get(payload, "prompt_cache", "expires_at")),
        recache_tokens=_int(_get(payload, "prompt_cache", "recache_tokens_if_cold")),
        session_cost_usd=_num(_get(payload, "cost", "total_cost_usd")),
        rate_limit_pct=_rate_limit_pct(rate_limits),
        # rate_limits is only sent to claude.ai subscribers.
        auth_mode="subscription" if isinstance(rate_limits, dict) else "api_key",
    )


def _base_line(snap: SessionSnapshot, now: datetime | None = None) -> str:
    parts = [snap.model_display_name or snap.model_id or "?"]
    if snap.context_used_pct is not None:
        parts.append(f"ctx {round(snap.context_used_pct)}%")
    if snap.cache_warm is True:
        minutes = cache_minutes_left(snap, now)
        parts.append(f"cache warm {minutes}m" if minutes is not None else "cache warm")
    elif snap.cache_warm is False:
        parts.append("cache cold")
    return " · ".join(parts)


def render(snap: SessionSnapshot, recs: list[Recommendation], color: bool = True, now: datetime | None = None) -> str:
    line = _base_line(snap, now)
    if not recs:
        return line
    top = recs[0]
    advice = f"{SEVERITY_MARK[top.severity]} {top.message} — run {top.action}"
    if color:
        advice = f"{ANSI[top.severity]}{advice}{ANSI['reset']}"
    return f"{line} · {advice}"


def status_line(raw: str, color: bool = True, now: datetime | None = None) -> str:
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return "windy: no session data"
        snap = to_snapshot(payload)
    except (json.JSONDecodeError, ValueError):
        return "windy: no session data"

    try:
        recs = evaluate(snap, get_advisor_config(), now)
    except Exception:  # broken advisor.yaml etc. — still show the base line
        return f"{_base_line(snap, now)} · windy: advisor error"
    return render(snap, recs, color=color, now=now)


def _capture(raw: str, argv: list[str]) -> None:
    """`--capture <path>`: save the raw payload (for building test fixtures)."""
    if "--capture" not in argv:
        return
    i = argv.index("--capture")
    if i + 1 < len(argv):
        try:
            with open(argv[i + 1], "w", encoding="utf-8") as f:
                f.write(raw)
        except OSError:
            pass


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    _capture(raw, sys.argv[1:])
    out = status_line(raw)
    sys.stdout.buffer.write(out.encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
