import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse, Response

from router.config import settings

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
    return _client


async def forward(request: Request, body: dict, routed_model: str) -> Response:
    body["model"] = routed_model

    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "transfer-encoding")
    }

    if settings.litellm_api_key:
        headers["authorization"] = f"Bearer {settings.litellm_api_key}"

    upstream_url = f"{settings.litellm_url}/v1/chat/completions"
    client = get_client()

    if body.get("stream"):
        return await _stream(client, upstream_url, headers, body)
    return await _complete(client, upstream_url, headers, body)


async def _complete(
    client: httpx.AsyncClient, url: str, headers: dict, body: dict
) -> Response:
    resp = await client.post(url, json=body, headers=headers)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type", "application/json"),
    )


async def _stream(
    client: httpx.AsyncClient, url: str, headers: dict, body: dict
) -> StreamingResponse:
    async def gen():
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            async for chunk in resp.aiter_bytes():
                yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")
