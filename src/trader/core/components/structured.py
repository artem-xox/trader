"""Lean structured output: one bound model call instead of an LCEL wrapper chain.

`model.with_structured_output(schema, method="function_calling", include_raw=True)` is
convenient but it expands into a tree of tracer-visible runnables wrapped around the single
ChatOpenAI call that does the work — RunnableParallel<raw>, RunnableWithFallbacks,
RunnableAssign<parsed,parsing_error>, PydanticToolsParser and a couple of RunnableLambdas.
That machinery dominates every trace.

`structured_call` reproduces the same contract — force exactly one tool call shaped like
`schema`, then parse its args — with a plain bound-model call, so a node leaves just its
ChatOpenAI span in the trace. Parsing is best-effort and returns ``None`` on failure,
leaving the recovery policy (a default, a prose fallback, …) to the caller.
"""

from __future__ import annotations

import json
from typing import TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


async def structured_call(
    model: BaseChatModel, schema: type[T], messages: list[BaseMessage]
) -> tuple[BaseMessage, T | None]:
    """Invoke `model` forcing one `schema`-shaped tool call; return ``(raw, parsed)``.

    `parsed` is ``None`` when the model returned no usable structured args — the caller
    decides how to recover. `raw` is always the model's message, so a caller can fall back
    to its text content.
    """
    bound = model.bind_tools([schema], tool_choice=schema.__name__)
    raw = await bound.ainvoke(messages)
    return raw, parse_structured(raw, schema)


def parse_structured(raw: BaseMessage, schema: type[T]) -> T | None:
    """Parse a `schema` out of a raw model message, returning ``None`` if nothing valid.

    In order of preference: the first tool call's args (the function-calling path), then the
    first JSON object embedded anywhere in the text content (a model that answered in prose
    around the JSON).
    """
    tool_calls = getattr(raw, "tool_calls", None)
    if tool_calls:
        try:
            return schema.model_validate(tool_calls[0]["args"])
        except ValidationError:
            pass

    content = raw.content if isinstance(raw.content, str) else str(raw.content)
    text = content.strip()
    brace = text.find("{")
    if brace != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[brace:])
            return schema.model_validate(obj)
        except (json.JSONDecodeError, ValidationError):
            pass
    return None
