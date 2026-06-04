# fs_agent/utils/stream_print.py
from __future__ import annotations

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


def print_clean_deepagent_stream(agent, payload: dict, show_tools: bool = True) -> str:
    """
    Clean console output for DeepAgent stream.

    Prints:
    - visible LLM text
    - optional tool calls

    Hides:
    - LangGraph metadata
    - checkpoint IDs
    - usage metadata
    - response metadata
    """
    full_text: list[str] = []
    printed_tool_call_ids: set[str] = set()

    last = None
    for mode, chunk in agent.stream(
        payload,
        stream_mode=["messages", "updates"],
    ):
        last = chunk
        if mode == "messages":
            message = _get_message(chunk)
            content = _get_content(message)

            if isinstance(content, str):
                if content:
                    print(content, end="", flush=True)
                    full_text.append(content)

            elif isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue

                    item_type = item.get("type")

                    if item_type == "text":
                        text = item.get("text", "")
                        if text:
                            print(text, end="", flush=True)
                            full_text.append(text)

                    elif show_tools and item_type == "function_call":
                        call_id = item.get("call_id") or item.get("id") or ""
                        name = item.get("name", "")
                        arguments = item.get("arguments", "")

                        # function_call 在流式输出中可能分片，避免重复打印空参数片段
                        key = f"{call_id}:{name}:{arguments}"
                        if name and key not in printed_tool_call_ids:
                            printed_tool_call_ids.add(key)
                            print(f"\n[tool call] {name} {arguments}", flush=True)

        elif mode == "updates" and show_tools:
            # 打印工具返回的 content，但不打印完整对象
            if isinstance(chunk, dict) and "tools" in chunk:
                tool_block = chunk["tools"]
                messages = tool_block.get("messages", []) if isinstance(tool_block, dict) else []

                for msg in messages:
                    name = getattr(msg, "name", None)
                    content = getattr(msg, "content", "")

                    if name:
                        short = str(content)
                        if len(short) > 1200:
                            short = short[:1200] + "\n...[truncated]"
                        print(f"\n[tool result] {name}:\n{short}", flush=True)

    print()
    return last
    return "".join(full_text)