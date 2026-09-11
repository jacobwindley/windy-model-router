import json

from router.proxy.metadata import RequestMetadata
from router.proxy.types import RouteInfo

TIERS = (
    {"tier": 1, "name": "rule-based"},
    {"tier": 2, "name": "weighted-scoring"},
    {"tier": 3, "name": "bandit"},
)

MATCHED_TIER = 1


def build_route_info_payload(route_info: RouteInfo, metadata: RequestMetadata) -> dict:
    return {
        "matched_tier": MATCHED_TIER,
        "decision": {
            "rule_id": route_info.rule_id,
            "reason": route_info.reason,
            "original_model": route_info.original_model,
            "routed_model": route_info.routed_model,
        },
        "metadata": {
            "token_count": metadata.token_count,
            "message_count": metadata.message_count,
            "tool_count": metadata.tool_count,
            "has_tools": metadata.has_tools,
            "has_multimodal": metadata.has_multimodal,
        },
        "tiers": [
            {
                **tier,
                "status": "matched" if tier["tier"] == MATCHED_TIER else "not_implemented",
            }
            for tier in TIERS
        ],
    }


def encode_route_info_header(payload: dict) -> str:
    # ensure_ascii=True is required, not incidental: Starlette encodes header
    # values as latin-1, so a non-ASCII `reason` string in rules.yaml would
    # otherwise crash the request.
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
