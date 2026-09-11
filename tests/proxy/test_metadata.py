from router.proxy.metadata import extract_metadata
from router.proxy.types import ChatCompletionRequest


def _request(**kwargs) -> ChatCompletionRequest:
    kwargs.setdefault("model", "fast-model")
    kwargs.setdefault("messages", [{"role": "user", "content": "hi"}])
    return ChatCompletionRequest.model_validate(kwargs)


def test_token_count_scales_with_text_length():
    short = extract_metadata(_request(messages=[{"role": "user", "content": "hi"}]))
    long = extract_metadata(
        _request(messages=[{"role": "user", "content": "hi " * 500}])
    )
    assert long.token_count > short.token_count


def test_message_count_matches_messages():
    meta = extract_metadata(
        _request(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ]
        )
    )
    assert meta.message_count == 3


def test_tool_count_and_has_tools_when_absent():
    meta = extract_metadata(_request())
    assert meta.tool_count == 0
    assert meta.has_tools is False


def test_tool_count_and_has_tools_when_present():
    meta = extract_metadata(
        _request(tools=[{"type": "function", "function": {"name": "a"}}, {"type": "function", "function": {"name": "b"}}])
    )
    assert meta.tool_count == 2
    assert meta.has_tools is True


def test_has_multimodal_false_for_text_only():
    meta = extract_metadata(
        _request(
            messages=[
                {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            ]
        )
    )
    assert meta.has_multimodal is False


def test_has_multimodal_true_for_image_part():
    meta = extract_metadata(
        _request(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "what's this"},
                        {"type": "image_url", "image_url": {"url": "http://example.com/x.png"}},
                    ],
                },
            ]
        )
    )
    assert meta.has_multimodal is True
