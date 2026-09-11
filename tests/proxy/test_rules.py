import pytest
import yaml

from router.proxy.metadata import RequestMetadata
from router.proxy.rules import RulesConfigError, evaluate_rules, load_rules

VALID_RULES = {
    "version": 1,
    "rules": [
        {
            "id": "tool-use",
            "match": {"has_tools": True},
            "route": "balanced-model",
            "reason": "has tools",
        },
        {
            "id": "large-context",
            "match": {"min_tokens": 100},
            "route": "smart-model",
            "reason": "big prompt",
        },
        {
            "id": "default",
            "match": {},
            "route": "fast-model",
            "reason": "fallback",
            "default": True,
        },
    ],
}


def _write_rules(tmp_path, data) -> str:
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return str(path)


def _meta(**kwargs) -> RequestMetadata:
    kwargs.setdefault("token_count", 0)
    kwargs.setdefault("message_count", 1)
    kwargs.setdefault("tool_count", 0)
    kwargs.setdefault("has_tools", False)
    kwargs.setdefault("has_multimodal", False)
    return RequestMetadata(**kwargs)


def test_load_rules_valid_yaml_preserves_order(tmp_path):
    rules = load_rules(_write_rules(tmp_path, VALID_RULES))
    assert [r.id for r in rules] == ["tool-use", "large-context", "default"]


def test_load_rules_missing_default_rule_raises(tmp_path):
    data = {"version": 1, "rules": [VALID_RULES["rules"][0]]}
    with pytest.raises(RulesConfigError):
        load_rules(_write_rules(tmp_path, data))


def test_load_rules_default_not_last_raises(tmp_path):
    data = {
        "version": 1,
        "rules": [VALID_RULES["rules"][2], VALID_RULES["rules"][0]],
    }
    with pytest.raises(RulesConfigError):
        load_rules(_write_rules(tmp_path, data))


def test_load_rules_default_with_nonempty_match_raises(tmp_path):
    bad_default = {**VALID_RULES["rules"][2], "match": {"has_tools": True}}
    data = {"version": 1, "rules": [VALID_RULES["rules"][0], bad_default]}
    with pytest.raises(RulesConfigError):
        load_rules(_write_rules(tmp_path, data))


def test_evaluate_rules_first_match_wins(tmp_path):
    rules = load_rules(_write_rules(tmp_path, VALID_RULES))
    meta = _meta(has_tools=True, token_count=500)
    route_info = evaluate_rules(meta, "gpt-4", rules)
    assert route_info.rule_id == "tool-use"
    assert route_info.routed_model == "balanced-model"


def test_evaluate_rules_falls_through_to_default(tmp_path):
    rules = load_rules(_write_rules(tmp_path, VALID_RULES))
    meta = _meta()
    route_info = evaluate_rules(meta, "gpt-4", rules)
    assert route_info.rule_id == "default"
    assert route_info.routed_model == "fast-model"
