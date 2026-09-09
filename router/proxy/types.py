from typing import Any, Literal
from pydantic import BaseModel


class ContentPart(BaseModel):
    type: str
    text: str | None = None
    image_url: dict | None = None

    model_config = {"extra": "allow"}


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool", "function"]
    content: str | list[ContentPart] | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    model_config = {"extra": "allow"}


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[Message]
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    tools: list[dict] | None = None
    functions: list[dict] | None = None
    response_format: dict | None = None
    seed: int | None = None
    stop: str | list[str] | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    logit_bias: dict | None = None
    user: str | None = None
    n: int | None = None

    model_config = {"extra": "allow"}


class RouteInfo(BaseModel):
    original_model: str
    routed_model: str
    rule_id: str
    reason: str
    token_count: int
