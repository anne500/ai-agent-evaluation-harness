"""Deterministic checks for the two-tool demo's returned message trace.

This validates recorded execution evidence, not independently observed side effects.
No LangChain or Ollama import is needed.
"""
import re
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ExecutionSpec:
    tool: str | None
    arguments: dict
    result_kind: str
    expected_count: int | None = None


def check_execution(messages, spec, started, finished):
    """Return named checks and reasons; require exactly one call when expected."""
    calls = []
    results = []
    malformed = False
    for position, message in enumerate(messages):
        malformed |= bool(getattr(message, "invalid_tool_calls", []))
        for call in getattr(message, "tool_calls", []) or []:
            calls.append((position, call))
        if getattr(message, "type", None) == "tool":
            results.append((position, message))

    checks = {
        "parseable_calls": not malformed,
        "call_count": len(calls) == (0 if spec.tool is None else 1),
        "tool_name": all(call.get("name") == spec.tool for _, call in calls),
        "arguments": all(call.get("args") == spec.arguments for _, call in calls),
        "result_pairing": False,
        "execution_status": False,
        "result_value": False,
        "final_answer": bool(messages)
        and getattr(messages[-1], "type", None) == "ai"
        and isinstance(getattr(messages[-1], "content", None), str)
        and bool(messages[-1].content.strip())
        and not getattr(messages[-1], "tool_calls", [])
        and not getattr(messages[-1], "invalid_tool_calls", []),
    }

    if spec.tool is None:
        checks["result_pairing"] = not results
        checks["execution_status"] = not results
        checks["result_value"] = not results
    elif len(calls) == len(results) == 1:
        call_position, call = calls[0]
        result_position, result = results[0]
        checks["result_pairing"] = (
            isinstance(call.get("id"), str)
            and bool(call["id"])
            and getattr(result, "tool_call_id", None) == call["id"]
            and call_position < result_position
            and getattr(result, "name", None) in (None, spec.tool)
        )
        checks["execution_status"] = getattr(result, "status", "success") == "success"
        value = getattr(result, "content", None)
        if spec.result_kind == "count":
            # LangChain normally serializes integer tool output as text.
            checks["result_value"] = (
                isinstance(value, str)
                and re.fullmatch(r"\d+", value.strip()) is not None
                and int(value.strip()) == spec.expected_count
            )
        elif spec.result_kind == "time":
            if isinstance(value, str) and re.fullmatch(
                r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value
            ):
                try:
                    observed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                    # Tool output has second precision; bounds use the same clock.
                    checks["result_value"] = (
                        started.replace(microsecond=0) <= observed <= finished
                    )
                except ValueError:
                    pass

    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "requested_tools": [call.get("name") for _, call in calls],
        "tool_results": [getattr(result, "content", None) for _, result in results],
    }
