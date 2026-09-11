import time
import structlog
from fastapi import Request
from fastapi.responses import Response

from router.proxy.types import ChatCompletionRequest
from router.proxy.forwarder import forward
from router.proxy.metadata import extract_metadata
from router.proxy.rules import get_rules, evaluate_rules
from router.proxy.route_info import build_route_info_payload, encode_route_info_header

log = structlog.get_logger()


async def handle_chat_completion(request: Request) -> Response:
    body = await request.json()
    req = ChatCompletionRequest.model_validate(body)

    metadata = extract_metadata(req)
    route_info = evaluate_rules(metadata, req.model, get_rules())

    start = time.monotonic()
    response = await forward(request, body, route_info.routed_model)
    latency_ms = round((time.monotonic() - start) * 1000)

    response.headers["X-Route-Info"] = encode_route_info_header(
        build_route_info_payload(route_info, metadata)
    )

    log.info(
        "routed",
        original_model=route_info.original_model,
        routed_model=route_info.routed_model,
        rule=route_info.rule_id,
        reason=route_info.reason,
        stream=req.stream,
        latency_ms=latency_ms,
        status=response.status_code,
    )

    return response
