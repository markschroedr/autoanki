from __future__ import annotations

import json
import threading
from importlib.resources import files

import quickjs


_THREAD_STATE = threading.local()


def _katex_context() -> quickjs.Context:
    context = getattr(_THREAD_STATE, "katex_context", None)
    if context is None:
        source = files("autoanki").joinpath("vendor/katex.min.js").read_text(encoding="utf-8")
        context = quickjs.Context()
        context.eval(source)
        _THREAD_STATE.katex_context = context
    return context


def validate_math(snippet: str) -> tuple[bool, str | None]:
    expression = json.dumps(snippet)
    try:
        _katex_context().eval(
            f"katex.renderToString({expression}, {{throwOnError: true, output: 'html'}})"
        )
    except quickjs.JSException as exc:
        message = str(exc).splitlines()[0]
        return False, message.removeprefix("ParseError: ")
    return True, None
