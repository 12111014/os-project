# fs_agent/utils/stream_print.py
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _get_message(chunk: Any) -> Any:
    if isinstance(chunk, tuple) and len(chunk) == 2:
        return chunk[0]
    return chunk


def _get_content(message: Any) -> Any:
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    return content


def _iter_text(content: Any) -> Iterable[str]:
    if isinstance(content, str):
        if content:
            yield content
        return

    if not isinstance(content, list):
        return

    for item in content:
        if isinstance(item, str):
            if item:
                yield item
            continue
        if not isinstance(item, dict):
            continue

        item_type = item.get("type")
        if item_type in {"text", "summary_text", "text_delta"}:
            text = item.get("text") or item.get("summary_text") or item.get("delta") or ""
            if text:
                yield text


def _iter_tool_calls(message: Any, content: Any) -> Iterable[tuple[str, str, str]]:
    for call in getattr(message, "tool_call_chunks", None) or []:
        if isinstance(call, dict):
            call_id = str(call.get("id") or call.get("call_id") or call.get("index") or "")
            name = str(call.get("name") or "")
            args = str(call.get("args") or call.get("arguments") or "")
            if name:
                yield call_id, name, args

    for call in getattr(message, "tool_calls", None) or []:
        if isinstance(call, dict):
            call_id = str(call.get("id") or call.get("call_id") or "")
            name = str(call.get("name") or "")
            args = str(call.get("args") or call.get("arguments") or "")
            if name:
                yield call_id, name, args

    additional = getattr(message, "additional_kwargs", None)
    if isinstance(additional, dict):
        for call in additional.get("tool_calls", []) or []:
            if not isinstance(call, dict):
                continue
            fn = call.get("function", {})
            if not isinstance(fn, dict):
                continue
            call_id = str(call.get("id") or "")
            name = str(fn.get("name") or "")
            args = str(fn.get("arguments") or "")
            if name:
                yield call_id, name, args

    if not isinstance(content, list):
        return

    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type not in {"function_call", "tool_use", "tool_call"}:
            continue
        call_id = str(item.get("call_id") or item.get("id") or "")
        name = str(item.get("name") or "")
        args = item.get("arguments", item.get("input", ""))
        if name:
            yield call_id, name, str(args)


def _iter_tool_arg_text(message: Any) -> Iterable[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()

    for attr in ("tool_call_chunks", "invalid_tool_calls"):
        for call in getattr(message, attr, None) or []:
            if not isinstance(call, dict):
                continue
            if call.get("name"):
                continue
            args = call.get("args") or call.get("arguments") or ""
            if not args:
                continue
            key = (str(call.get("id") or call.get("index") or ""), str(args))
            if key in seen:
                continue
            seen.add(key)
            yield attr, str(args)


def print_clean_deepagent_stream(agent, payload: dict, context, show_tools: bool = True) -> dict[str, Any]:
    final_values: dict[str, Any] | None = None
    printed_tool_calls: set[str] = set()

    for mode, chunk in agent.stream(
        payload,
        context=context,
        stream_mode=["messages", "values"],
    ):
        if mode == "values":
            if isinstance(chunk, dict):
                final_values = chunk
            continue

        if mode != "messages":
            continue

        message = _get_message(chunk)
        content = _get_content(message)

        for text in _iter_text(content):
            print(text, end="", flush=False)

        if show_tools:
            for _, text in _iter_tool_arg_text(message):
                print(text, end="", flush=False)

        if not show_tools:
            continue

        for call_id, name, arguments in _iter_tool_calls(message, content):
            key = call_id or name
            if key in printed_tool_calls:
                continue
            printed_tool_calls.add(key)
            suffix = f" {arguments}" if arguments else ""
            print(f"\n[tool call] {name}{suffix}", flush=False)

    print()

    if final_values is None:
        raise RuntimeError("DeepAgent stream completed without final values output.")
    return final_values
