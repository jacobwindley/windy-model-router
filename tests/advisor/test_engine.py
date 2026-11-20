from datetime import datetime, timedelta, timezone

import pytest
import yaml

from router.advisor.engine import (
    DEFAULT_CONFIG_PATH,
    AdvisorConfigError,
    evaluate,
    load_advisor_config,
    model_family,
)
from router.advisor.snapshot import SessionSnapshot

NOW = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def config():
    return load_advisor_config(DEFAULT_CONFIG_PATH)


def _snap(**kwargs) -> SessionSnapshot:
    kwargs.setdefault("harness", "test")
    kwargs.setdefault("model_id", "claude-opus-5-5")
    return SessionSnapshot(**kwargs)


def _ids(recs):
    return [r.id for r in recs]


def test_shipped_config_loads(config):
    assert config.rules


def test_no_recommendations_for_healthy_session(config):
    snap = _snap(context_used_pct=30, auth_mode="subscription", rate_limit_pct=10)
    assert evaluate(snap, config, NOW) == []


def test_context_threshold(config):
    assert _ids(evaluate(_snap(context_used_pct=69.9), config, NOW)) == []
    recs = evaluate(_snap(context_used_pct=74), config, NOW)
    assert _ids(recs) == ["context-high"]
    assert recs[0].action == "/compact"
    assert "74%" in recs[0].message


def test_all_matching_rules_fire_most_severe_first(config):
    recs = evaluate(_snap(context_used_pct=92), config, NOW)
    assert _ids(recs) == ["context-critical", "context-high"]


def test_missing_signal_never_matches_threshold(config):
    assert evaluate(_snap(context_used_pct=None), config, NOW) == []


def test_rate_limit_only_for_subscription(config):
    sub = evaluate(_snap(auth_mode="subscription", rate_limit_pct=80), config, NOW)
    assert _ids(sub) == ["rate-limit-pressure"]
    assert sub[0].action == "/model sonnet"

    api = evaluate(_snap(auth_mode="api_key", rate_limit_pct=80), config, NOW)
    assert api == []


def test_session_cost_only_for_api_key(config):
    recs = evaluate(_snap(auth_mode="api_key", session_cost_usd=7.5), config, NOW)
    assert _ids(recs) == ["session-cost"]
    assert "$7.50" in recs[0].message
    assert evaluate(_snap(auth_mode="subscription", session_cost_usd=7.5), config, NOW) == []


@pytest.mark.parametrize(
    "model_id, expected_action",
    [
        ("claude-opus-5-5", "/model sonnet"),
        ("claude-sonnet-5-5", "/model haiku"),
        ("claude-haiku-5-5", None),  # bottom of the ladder: no suggestion
        ("some-unknown-model", None),
    ],
)
def test_downshift_ladder(config, model_id, expected_action):
    recs = evaluate(_snap(model_id=model_id, auth_mode="subscription", rate_limit_pct=90), config, NOW)
    actions = [r.action for r in recs]
    assert actions == ([expected_action] if expected_action else [])


def test_cache_warm_note_on_switch(config):
    snap = _snap(
        auth_mode="subscription",
        rate_limit_pct=90,
        cache_warm=True,
        cache_expires_at=NOW + timedelta(minutes=3, seconds=20),
        input_tokens=2000,
        cache_read_tokens=78000,
        cache_creation_tokens=4000,
    )
    [rec] = evaluate(snap, config, NOW)
    assert "re-sends ~84k tokens uncached" in rec.message
    assert "cache cools in 3m" in rec.message


def test_no_cache_note_when_cold(config):
    snap = _snap(auth_mode="subscription", rate_limit_pct=90, cache_warm=False, input_tokens=50000)
    [rec] = evaluate(snap, config, NOW)
    assert "uncached" not in rec.message


def test_model_family():
    assert model_family("claude-opus-5-5") == "opus"
    assert model_family("us.anthropic.claude-sonnet-5-5") == "sonnet"
    assert model_family("claude-fable-5-2") == "fable"
    assert model_family(None) is None
    assert model_family("gpt-x") is None


def _write(tmp_path, data):
    path = tmp_path / "advisor.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def _rule(**overrides):
    rule = {
        "id": "r",
        "match": {"min_context_pct": 50},
        "kind": "compact",
        "severity": "warn",
        "message": "m",
        "action": "/compact",
    }
    rule.update(overrides)
    return rule


def test_typoed_match_key_fails_loudly(tmp_path):
    path = _write(tmp_path, {"version": 1, "rules": [_rule(match={"min_contxt_pct": 50})]})
    with pytest.raises(ValueError):
        load_advisor_config(path)


def test_duplicate_ids_rejected(tmp_path):
    path = _write(tmp_path, {"version": 1, "rules": [_rule(), _rule()]})
    with pytest.raises(AdvisorConfigError):
        load_advisor_config(path)


def test_empty_match_rejected(tmp_path):
    path = _write(tmp_path, {"version": 1, "rules": [_rule(match={})]})
    with pytest.raises(AdvisorConfigError):
        load_advisor_config(path)


def test_min_context_tokens(config):
    assert evaluate(_snap(cache_read_tokens=299_000), config, NOW) == []
    recs = evaluate(_snap(cache_read_tokens=300_000), config, NOW)
    assert _ids(recs) == ["context-large"]
    assert "~300k" in recs[0].message


def test_cache_note_prefers_reported_recache_tokens(config):
    snap = _snap(
        auth_mode="subscription", rate_limit_pct=90, cache_warm=True,
        input_tokens=10, cache_read_tokens=10, recache_tokens=99_900,
    )
    [rec] = evaluate(snap, config, NOW)
    assert "re-sends ~100k tokens uncached" in rec.message
