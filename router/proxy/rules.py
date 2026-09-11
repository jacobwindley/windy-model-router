from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from router.config import settings
from router.proxy.metadata import RequestMetadata
from router.proxy.types import RouteInfo


class RuleMatch(BaseModel):
    min_tokens: int | None = None
    max_tokens: int | None = None
    min_messages: int | None = None
    max_messages: int | None = None
    min_tools: int | None = None
    has_tools: bool | None = None
    has_multimodal: bool | None = None

    model_config = {"extra": "forbid"}


class Rule(BaseModel):
    id: str
    match: RuleMatch = RuleMatch()
    route: str
    reason: str
    default: bool = False


class RulesConfigError(ValueError):
    pass


def _validate_catch_all(rules: list[Rule]) -> None:
    default_rules = [r for r in rules if r.default]

    if len(default_rules) != 1:
        raise RulesConfigError(
            f"rules.yaml must have exactly one rule with `default: true`, found {len(default_rules)}"
        )
    if rules[-1] is not default_rules[0]:
        raise RulesConfigError("the default rule must be the last rule in the list")
    if default_rules[0].match != RuleMatch():
        raise RulesConfigError("the default rule's `match` block must be empty so it always matches")


def load_rules(path: str | Path) -> list[Rule]:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    rules = [Rule.model_validate(r) for r in raw["rules"]]
    _validate_catch_all(rules)
    return rules


@lru_cache(maxsize=1)
def get_rules() -> list[Rule]:
    return load_rules(settings.rules_path)


def _matches(meta: RequestMetadata, match: RuleMatch) -> bool:
    if match.min_tokens is not None and meta.token_count < match.min_tokens:
        return False
    if match.max_tokens is not None and meta.token_count > match.max_tokens:
        return False
    if match.min_messages is not None and meta.message_count < match.min_messages:
        return False
    if match.max_messages is not None and meta.message_count > match.max_messages:
        return False
    if match.min_tools is not None and meta.tool_count < match.min_tools:
        return False
    if match.has_tools is not None and meta.has_tools != match.has_tools:
        return False
    if match.has_multimodal is not None and meta.has_multimodal != match.has_multimodal:
        return False
    return True


def evaluate_rules(meta: RequestMetadata, original_model: str, rules: list[Rule]) -> RouteInfo:
    for rule in rules:
        if _matches(meta, rule.match):
            return RouteInfo(
                original_model=original_model,
                routed_model=rule.route,
                rule_id=rule.id,
                reason=rule.reason,
                token_count=meta.token_count,
            )

    raise RulesConfigError("no rule matched and no default rule was found")
