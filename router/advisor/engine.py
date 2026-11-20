"""Session advisor: turns a SessionSnapshot into recommendations.

Unlike the Tier-1 routing rules (first match wins), every matching advisor rule
fires; results are ordered most-severe first so a one-line display can show the
top one.
"""

import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from router.advisor.snapshot import AuthMode, SessionSnapshot

# Resolved relative to the repo, not the cwd: harness integrations (e.g. a Claude
# Code status line) run with cwd set to the *user's* project.
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "advisor.yaml"
CONFIG_ENV_VAR = "WINDY_ADVISOR_CONFIG"

Severity = Literal["info", "warn", "critical"]
Kind = Literal["compact", "clear", "switch_model"]
ModelFamily = Literal["fable", "opus", "sonnet", "haiku"]

SEVERITY_RANK: dict[str, int] = {"info": 0, "warn": 1, "critical": 2}
MODEL_FAMILIES: tuple[str, ...] = ("fable", "opus", "sonnet", "haiku")


class AdvisorConfigError(ValueError):
    pass


class AdvisorMatch(BaseModel):
    min_context_pct: float | None = None
    min_context_tokens: int | None = None
    auth_mode: AuthMode | None = None
    min_rate_limit_pct: float | None = None
    min_session_cost_usd: float | None = None
    model_family: ModelFamily | None = None

    model_config = {"extra": "forbid"}


class AdvisorRule(BaseModel):
    id: str
    match: AdvisorMatch
    kind: Kind
    severity: Severity
    message: str
    action: str

    model_config = {"extra": "forbid"}


class AdvisorConfig(BaseModel):
    version: int
    downshift: dict[ModelFamily, ModelFamily] = {}
    rules: list[AdvisorRule]

    model_config = {"extra": "forbid"}


class Recommendation(BaseModel):
    id: str
    kind: Kind
    severity: Severity
    message: str
    action: str


def load_advisor_config(path: str | Path) -> AdvisorConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    config = AdvisorConfig.model_validate(raw)

    ids = [r.id for r in config.rules]
    if len(ids) != len(set(ids)):
        raise AdvisorConfigError("advisor rule ids must be unique")
    for rule in config.rules:
        if rule.match == AdvisorMatch():
            raise AdvisorConfigError(f"advisor rule {rule.id!r} has an empty match and would always fire")
    return config


@lru_cache(maxsize=1)
def get_advisor_config() -> AdvisorConfig:
    return load_advisor_config(os.environ.get(CONFIG_ENV_VAR) or DEFAULT_CONFIG_PATH)


def model_family(model_id: str | None) -> str | None:
    if not model_id:
        return None
    lowered = model_id.lower()
    for family in MODEL_FAMILIES:
        if family in lowered:
            return family
    return None


def _matches(snap: SessionSnapshot, match: AdvisorMatch) -> bool:
    # A threshold on a signal the harness didn't report never matches.
    if match.min_context_pct is not None:
        if snap.context_used_pct is None or snap.context_used_pct < match.min_context_pct:
            return False
    if match.min_context_tokens is not None:
        if snap.prompt_tokens is None or snap.prompt_tokens < match.min_context_tokens:
            return False
    if match.auth_mode is not None and snap.auth_mode != match.auth_mode:
        return False
    if match.min_rate_limit_pct is not None:
        if snap.rate_limit_pct is None or snap.rate_limit_pct < match.min_rate_limit_pct:
            return False
    if match.min_session_cost_usd is not None:
        if snap.session_cost_usd is None or snap.session_cost_usd < match.min_session_cost_usd:
            return False
    if match.model_family is not None and model_family(snap.model_id) != match.model_family:
        return False
    return True


def _format_tokens(n: int) -> str:
    return f"~{round(n / 1000)}k" if n >= 1000 else str(n)


def cache_minutes_left(snap: SessionSnapshot, now: datetime | None = None) -> int | None:
    if snap.cache_expires_at is None:
        return None
    now = now or datetime.now(timezone.utc)
    seconds = (snap.cache_expires_at - now).total_seconds()
    return max(0, int(seconds // 60))


def _cache_note(snap: SessionSnapshot, now: datetime | None) -> str | None:
    if not snap.cache_warm:
        return None
    parts = []
    if resend := snap.recache_tokens or snap.prompt_tokens:
        parts.append(f"switching now re-sends {_format_tokens(resend)} tokens uncached")
    else:
        parts.append("switching now discards the warm prompt cache")
    minutes = cache_minutes_left(snap, now)
    if minutes is not None:
        parts.append(f"cache cools in {minutes}m")
    return "; ".join(parts)


def evaluate(
    snap: SessionSnapshot, config: AdvisorConfig, now: datetime | None = None
) -> list[Recommendation]:
    family = model_family(snap.model_id)
    results: list[Recommendation] = []

    for rule in config.rules:
        if not _matches(snap, rule.match):
            continue

        fields = {
            "context_pct": round(snap.context_used_pct) if snap.context_used_pct is not None else "?",
            "context_tokens": _format_tokens(snap.prompt_tokens) if snap.prompt_tokens is not None else "?",
            "rate_limit_pct": round(snap.rate_limit_pct) if snap.rate_limit_pct is not None else "?",
            "session_cost": f"{snap.session_cost_usd:.2f}" if snap.session_cost_usd is not None else "?",
            "model": family or snap.model_id or "?",
            "target": "?",
        }

        if rule.kind == "switch_model":
            target = config.downshift.get(family) if family else None
            if target is None:
                continue  # nothing cheaper to suggest from this model
            fields["target"] = target

        message = rule.message.format(**fields)
        if rule.kind == "switch_model" and (note := _cache_note(snap, now)):
            message = f"{message} ({note})"

        results.append(
            Recommendation(
                id=rule.id,
                kind=rule.kind,
                severity=rule.severity,
                message=message,
                action=rule.action.format(**fields),
            )
        )

    results.sort(key=lambda r: SEVERITY_RANK[r.severity], reverse=True)
    return results
