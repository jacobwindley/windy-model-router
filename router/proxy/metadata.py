import tiktoken
from pydantic import BaseModel

from router.proxy.types import ChatCompletionRequest

# Fixed encoding rather than tiktoken.encoding_for_model(): our model aliases
# (fast-model, etc.) aren't real OpenAI model names and would raise KeyError.
# token_count is therefore a size estimate for routing thresholds, not a
# billing-accurate count (no per-message ChatML overhead added).
_ENCODING = tiktoken.get_encoding("cl100k_base")


class RequestMetadata(BaseModel):
    token_count: int
    message_count: int
    tool_count: int
    has_tools: bool
    has_multimodal: bool


def _count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def extract_metadata(req: ChatCompletionRequest) -> RequestMetadata:
    token_count = 0
    has_multimodal = False

    for message in req.messages:
        content = message.content
        if isinstance(content, str):
            token_count += _count_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if part.type == "text" and part.text:
                    token_count += _count_tokens(part.text)
                elif part.type != "text":
                    has_multimodal = True

    tool_count = len(req.tools or [])

    return RequestMetadata(
        token_count=token_count,
        message_count=len(req.messages),
        tool_count=tool_count,
        has_tools=tool_count > 0,
        has_multimodal=has_multimodal,
    )
