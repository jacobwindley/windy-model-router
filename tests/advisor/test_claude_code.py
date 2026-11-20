import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from router.advisor.claude_code import status_line, to_snapshot

EXPIRES = datetime(2026, 11, 20, 8, 51, 13, tzinfo=timezone.utc)
FIXTURE = Path(__file__).parent / "fixtures" / "claude_code_statusline.json"
NOW = datetime(2026, 11, 20, 8, 47, tzinfo=timezone.utc)  # fixture cache expires 08:51:13


@pytest.fixture
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_maps_to_snapshot(payload):
    snap = to_snapshot(payload)
    assert snap.harness == "claude_code"
    assert snap.model_id == "claude-opus-5-5"
    assert snap.context_used_pct == 10
    assert snap.context_window_size == 1_000_000
    assert snap.prompt_tokens == 101_300
    assert snap.recache_tokens == 99_900
    assert snap.cache_warm is True
    assert snap.cache_expires_at == EXPIRES
    assert snap.session_cost_usd == 1.90099816
    assert snap.rate_limit_pct == 42  # max of five_hour (7) and seven_day (42)
    assert snap.auth_mode == "subscription"


def test_no_rate_limits_means_api_key(payload):
    del payload["rate_limits"]
    snap = to_snapshot(payload)
    assert snap.auth_mode == "api_key"
    assert snap.rate_limit_pct is None


def test_epoch_expiry_parsed(payload):
    payload["prompt_cache"]["expires_at"] = int(EXPIRES.timestamp() * 1000)
    assert to_snapshot(payload).cache_expires_at == EXPIRES
    payload["prompt_cache"]["expires_at"] = EXPIRES.isoformat()
    assert to_snapshot(payload).cache_expires_at == EXPIRES


def test_healthy_line(payload):
    line = status_line(json.dumps(payload), color=False, now=NOW)
    assert line == "Opus 5.5 · ctx 10% · cache warm 4m"


def test_critical_context_line(payload):
    payload["context_window"]["used_percentage"] = 92
    line = status_line(json.dumps(payload), color=False, now=NOW)
    assert line == "Opus 5.5 · ctx 92% · cache warm 4m · ⚠ context 92% full — run /compact or /clear"


def test_rate_limit_switch_line(payload):
    payload["rate_limits"]["five_hour"]["used_percentage"] = 81
    line = status_line(json.dumps(payload), color=False, now=NOW)
    assert "rate limit 81% used; sonnet stretches it further" in line
    assert "re-sends ~100k tokens uncached; cache cools in 4m" in line
    assert line.endswith("run /model sonnet")


def test_color_wraps_advice(payload):
    payload["context_window"]["used_percentage"] = 75
    line = status_line(json.dumps(payload), color=True, now=NOW)
    assert "\033[33m" in line and line.endswith("\033[0m")


@pytest.mark.parametrize("raw", ["", "not json", "[]", "null", '{"session_id": 123}'])
def test_garbage_input_never_raises(raw):
    assert status_line(raw, color=False, now=NOW)


def test_sparse_payload(payload):
    sparse = {"model": {"id": "claude-sonnet-5-5"}}
    assert status_line(json.dumps(sparse), color=False, now=NOW) == "claude-sonnet-5-5"


def test_unexpected_shapes_degrade_to_none(payload):
    weird = copy.deepcopy(payload)
    weird["context_window"] = "oops"
    weird["prompt_cache"] = {"warm": "yes", "expires_at": "not a date"}
    weird["rate_limits"] = {"five_hour": 5}
    snap = to_snapshot(weird)
    assert snap.context_used_pct is None
    assert snap.cache_warm is None
    assert snap.cache_expires_at is None
    assert snap.rate_limit_pct is None


def test_large_context_on_1m_window(payload):
    usage = payload["context_window"]["current_usage"]
    usage["cache_read_input_tokens"] = 350_000
    payload["context_window"]["used_percentage"] = 35  # under the % thresholds
    line = status_line(json.dumps(payload), color=False, now=NOW)
    assert line.endswith("⚠ context ~351k tokens; every turn re-reads it — run /compact")
