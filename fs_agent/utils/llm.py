"""Thin LLM helper for the filesystem agent.

The rest of the agent should never import ``anthropic`` / ``langchain``
directly. It calls :func:`generate_text` and, when the model is not
configured (missing dependency or missing API key), catches
:class:`LLMUnavailable` and falls back to a deterministic path (e.g. copying
a known-good template).

Configuration via environment variables:
    ANTHROPIC_API_KEY   required to enable the LLM.
    FS_AGENT_MODEL      model id (default: claude-sonnet-4-6).
    FS_AGENT_MAX_TOKENS max output tokens (default: 16000).
"""

from __future__ import annotations

import os

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 16000


class LLMUnavailable(RuntimeError):
    """Raised when no usable LLM backend is configured."""


def is_available() -> bool:
    """Cheap check: do we have an API key in the environment?"""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _model_name() -> str:
    return os.environ.get("FS_AGENT_MODEL", DEFAULT_MODEL)


def _max_tokens() -> int:
    try:
        return int(os.environ.get("FS_AGENT_MAX_TOKENS", DEFAULT_MAX_TOKENS))
    except ValueError:
        return DEFAULT_MAX_TOKENS


def generate_text(system: str, user: str) -> str:
    """Run a single-shot completion and return the model's text.

    Prefers ``langchain_anthropic`` (matches the LangGraph stack) and falls
    back to the raw ``anthropic`` SDK. Raises :class:`LLMUnavailable` if
    neither is installed or no API key is present.
    """
    if not is_available():
        raise LLMUnavailable(
            "ANTHROPIC_API_KEY is not set; cannot call the LLM."
        )

    model = _model_name()
    max_tokens = _max_tokens()

    # Preferred: langchain-anthropic (consistent with the rest of the stack).
    try:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatAnthropic(model=model, max_tokens=max_tokens, timeout=600)
        resp = llm.invoke([SystemMessage(system), HumanMessage(user)])
        return _as_text(resp.content)
    except ImportError:
        pass

    # Fallback: the raw anthropic SDK.
    try:
        import anthropic
    except ImportError as exc:  # neither backend available
        raise LLMUnavailable(
            "Neither langchain_anthropic nor anthropic is installed."
        ) from exc

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(
        block.text for block in msg.content if getattr(block, "type", "") == "text"
    )


def _as_text(content) -> str:
    """Normalise langchain message content (str or list of blocks) to text."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)
