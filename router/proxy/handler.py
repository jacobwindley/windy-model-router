import time
import structlog
from fastapi import Request
from fastapi.responses import Response

from router.proxy.types import ChatCompletionRequest
from router.proxy.forwarder import forward

log = structlog.get_logger()


async def handle_chat_completion(request: Request) -> Response:
    body = await request.json()
    req = ChatCompletionRequest.model_validate(body)

    # Phase 1: pass-through — route to whatever model was requested
    # Phases 2-3 will replace this with extract → route → decision
    routed_model = req.model
    rule_id = "passthrough"

    start = time.monotonic()
    response = await forward(request, body, routed_model)
    latency_ms = round((time.monotonic() - start) * 1000)

    log.info(
        "routed",
        original_model=req.model,
        routed_model=routed_model,
        rule=rule_id,
        stream=req.stream,
        latency_ms=latency_ms,
        status=response.status_code,
    )

    return response
