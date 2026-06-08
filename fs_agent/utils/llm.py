"""Multi-provider LLM helper for the filesystem agent.

The rest of the agent never imports a vendor SDK directly. It calls
:func:`generate_text` and, when no provider is usable (missing dependency or
missing API key), catches :class:`LLMUnavailable` and falls back to a
deterministic path (e.g. copying a known-good template).

Supported providers (env var selects which):
    anthropic   Claude          key: ANTHROPIC_API_KEY
    openai      GPT             key: OPENAI_API_KEY
    deepseek    DeepSeek        key: DEEPSEEK_API_KEY   (OpenAI-compatible)
    qwen        Alibaba Qwen    key: DASHSCOPE_API_KEY  (OpenAI-compatible)
    google      Gemini          key: GOOGLE_API_KEY
    openai_compatible   any OpenAI-compatible endpoint
                        key: FS_AGENT_API_KEY, base url: FS_AGENT_BASE_URL

Configuration via environment variables:
    FS_AGENT_PROVIDER   force a provider (one of the names above). If unset,
                        the first provider with a key present is used, in the
                        order listed in PROVIDER_PRIORITY.
    FS_AGENT_MODEL      override the model id (else the provider default).
    FS_AGENT_BASE_URL   override the base url (OpenAI-compatible providers).
    FS_AGENT_MAX_TOKENS max output tokens (default: 16000).

DeepSeek, Qwen, OpenAI and any other OpenAI-compatible service all go through
the ``openai`` Python SDK with a per-provider ``base_url``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MAX_TOKENS = 16000


class LLMUnavailable(RuntimeError):
    """Raised when no usable LLM backend is configured."""


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    key_env: str
    default_model: str
    kind: str                 # "anthropic" | "openai" | "google"
    base_url: str | None = None


# Registry of known providers.
PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        "anthropic", "ANTHROPIC_API_KEY", "claude-sonnet-4-6", "anthropic"
    ),
    "openai": ProviderSpec(
        "openai", "OPENAI_API_KEY", "gpt-4o", "openai"
    ),
    "deepseek": ProviderSpec(
        "deepseek", "DEEPSEEK_API_KEY", "deepseek-chat", "openai",
        base_url="https://api.deepseek.com",
    ),
    "qwen": ProviderSpec(
        "qwen", "DASHSCOPE_API_KEY", "qwen3.7-max", "openai",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    "google": ProviderSpec(
        "google", "GOOGLE_API_KEY", "gemini-1.5-pro", "google"
    ),
    "openai_compatible": ProviderSpec(
        "openai_compatible", "FS_AGENT_API_KEY", "", "openai"
    ),
}

# Order used for auto-detection when FS_AGENT_PROVIDER is not set.
PROVIDER_PRIORITY = ["anthropic", "openai", "deepseek", "qwen", "google",
                     "openai_compatible"]


def _max_tokens() -> int:
    try:
        return int(os.environ.get("FS_AGENT_MAX_TOKENS", DEFAULT_MAX_TOKENS))
    except ValueError:
        return DEFAULT_MAX_TOKENS


def resolve_provider() -> ProviderSpec | None:
    """Return the provider to use, or None if none is configured.

    Honours FS_AGENT_PROVIDER; otherwise picks the first provider in
    PROVIDER_PRIORITY whose API key is present in the environment.
    """
    forced = os.environ.get("FS_AGENT_PROVIDER", "").strip().lower()
    if forced:
        spec = PROVIDERS.get(forced)
        if spec is None:
            raise LLMUnavailable(
                f"Unknown FS_AGENT_PROVIDER='{forced}'. "
                f"Valid: {', '.join(PROVIDERS)}"
            )
        if not os.environ.get(spec.key_env):
            raise LLMUnavailable(
                f"Provider '{forced}' selected but {spec.key_env} is not set."
            )
        return spec

    for name in PROVIDER_PRIORITY:
        spec = PROVIDERS[name]
        if os.environ.get(spec.key_env):
            return spec
    return None


def _model_for(spec: ProviderSpec) -> str:
    override = os.environ.get("FS_AGENT_MODEL", "").strip()
    if override:
        return override
    if not spec.default_model:
        raise LLMUnavailable(
            f"Provider '{spec.name}' has no default model; set FS_AGENT_MODEL."
        )
    return spec.default_model


def _base_url_for(spec: ProviderSpec) -> str | None:
    return os.environ.get("FS_AGENT_BASE_URL", "").strip() or spec.base_url


def is_available() -> bool:
    """True if some provider with an API key is configured."""
    try:
        return resolve_provider() is not None
    except LLMUnavailable:
        return False


def generate_text(system: str, user: str) -> str:
    """Run a single-shot completion and return the model's text.

    Raises :class:`LLMUnavailable` if no provider is configured or the
    selected provider's SDK is not installed.
    """
    spec = resolve_provider()
    if spec is None:
        raise LLMUnavailable(
            "No LLM provider configured. Set one of: "
            + ", ".join(p.key_env for p in PROVIDERS.values())
        )

    model = _model_for(spec)
    max_tokens = _max_tokens()

    if spec.kind == "anthropic":
        return _call_anthropic(model, max_tokens, system, user)
    if spec.kind == "openai":
        return _call_openai(spec, model, max_tokens, system, user)
    if spec.kind == "google":
        return _call_google(model, max_tokens, system, user)
    raise LLMUnavailable(f"Unsupported provider kind '{spec.kind}'.")


# ---- per-kind backends ----

def _call_anthropic(model: str, max_tokens: int, system: str, user: str) -> str:
    # Prefer langchain-anthropic (consistent with the LangGraph stack).
    try:
        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatAnthropic(model=model, max_tokens=max_tokens, timeout=600)
        resp = llm.invoke([SystemMessage(system), HumanMessage(user)])
        return _as_text(resp.content)
    except ImportError:
        pass

    try:
        import anthropic
    except ImportError as exc:
        raise LLMUnavailable(
            "anthropic provider requires `pip install anthropic` "
            "(or langchain-anthropic)."
        ) from exc

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(
        b.text for b in msg.content if getattr(b, "type", "") == "text"
    )


def _call_openai(spec: ProviderSpec, model: str, max_tokens: int,
                 system: str, user: str) -> str:
    """OpenAI and all OpenAI-compatible services (DeepSeek, Qwen, ...)."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMUnavailable(
            f"provider '{spec.name}' requires `pip install openai`."
        ) from exc

    api_key = os.environ.get(spec.key_env)
    base_url = _base_url_for(spec)
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=600)
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def _call_google(model: str, max_tokens: int, system: str, user: str) -> str:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import SystemMessage, HumanMessage
    except ImportError as exc:
        raise LLMUnavailable(
            "google provider requires `pip install langchain-google-genai`."
        ) from exc

    llm = ChatGoogleGenerativeAI(model=model, max_output_tokens=max_tokens)
    resp = llm.invoke([SystemMessage(system), HumanMessage(user)])
    return _as_text(resp.content)


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
