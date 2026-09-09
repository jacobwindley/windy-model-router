import structlog
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from router.config import settings
from router.proxy.handler import handle_chat_completion

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level.upper(), logging.INFO)
    ),
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("windy-model-router starting", litellm_url=settings.litellm_url)
    yield
    log.info("windy-model-router stopping")


app = FastAPI(title="windy-model-router", lifespan=lifespan)


def _check_auth(request: Request):
    if not settings.router_api_key:
        return
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if token != settings.router_api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    _check_auth(request)
    return await handle_chat_completion(request)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/admin/stats")
async def admin_stats():
    # Phase 4 will populate real stats
    return {"message": "stats not yet implemented"}


@app.get("/admin/models")
async def admin_models():
    # Phase 3 will populate the model registry
    return {"message": "model registry not yet implemented"}
