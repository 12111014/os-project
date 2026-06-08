"""Helpers for the code generator agent.

Kept separate from the agent so the prompt-building / grounding logic (loading
the libfuse reference examples and the known-good skeleton) can be unit-tested
without LangGraph or a live LLM.
"""

from __future__ import annotations

from pathlib import Path

# Repository roots (this file lives at fs_agent/utils/codegen.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "fs" / "libfuse" / "example"
TEMPLATES_DIR = REPO_ROOT / "templates"

# Which libfuse example sources to show the model, by storage type. These are
# all high-level API (fuse.h / struct fuse_operations), matching the template.
_REFERENCE_MAP = {
    "memory": ["hello.c", "passthrough.c"],
    "passthrough": ["passthrough.c", "passthrough_fh.c"],
}
_DEFAULT_REFERENCES = ["hello.c", "passthrough.c"]


def fallback_template_dir(fs_ir: dict) -> Path:
    """Pick the known-good template directory used to ground the agent."""
    storage_type = (fs_ir.get("storage", {}) or {}).get("type", "memory")
    if storage_type == "passthrough":
        candidate = TEMPLATES_DIR / "passthrough_ll"
        if candidate.exists():
            return candidate
    return TEMPLATES_DIR / "memfs"


def select_reference_examples(fs_ir: dict, max_chars: int = 24000) -> dict[str, str]:
    """Load relevant libfuse example sources to ground the model.

    Each source is truncated to ``max_chars`` to keep the prompt bounded.
    """
    storage_type = (fs_ir.get("storage", {}) or {}).get("type", "memory")
    names = _REFERENCE_MAP.get(storage_type, _DEFAULT_REFERENCES)
    out: dict[str, str] = {}
    for name in names:
        path = EXAMPLES_DIR / name
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            if len(text) > max_chars:
                text = text[:max_chars] + "\n/* ...truncated... */\n"
            out[name] = text
    return out


def load_template_skeleton(fs_ir: dict) -> tuple[str, str]:
    """Return (filename, source) of the known-good template as a skeleton."""
    tdir = fallback_template_dir(fs_ir)
    for candidate in ("memfs.c", "passthrough_ll.c"):
        p = tdir / candidate
        if p.exists():
            return candidate, p.read_text(encoding="utf-8", errors="replace")
    return "", ""


def build_user_prompt(fs_ir: dict, architecture_plan: dict) -> str:
    """Assemble the user prompt: spec + architecture + references + skeleton."""
    import json

    references = select_reference_examples(fs_ir)
    skel_name, skel_src = load_template_skeleton(fs_ir)

    parts: list[str] = []
    parts.append("# Filesystem specification (FilesystemIR)\n")
    parts.append("```json\n" + json.dumps(fs_ir, indent=2, ensure_ascii=False) + "\n```\n")

    parts.append("# Architecture plan\n")
    parts.append(
        "```json\n" + json.dumps(architecture_plan, indent=2, ensure_ascii=False) + "\n```\n"
    )

    if skel_src:
        parts.append(
            f"# Known-good skeleton ({skel_name})\n"
            "This is a correct, compiling reference for this exact libfuse "
            "version. Prefer adapting it over writing from scratch.\n"
        )
        parts.append(f"```c\n{skel_src}\n```\n")

    if references:
        parts.append("# Additional libfuse reference examples\n")
        for name, src in references.items():
            parts.append(f"## {name}\n```c\n{src}\n```\n")

    parts.append(
        "# Task\n"
        "Generate a complete, buildable FUSE filesystem that satisfies the "
        "specification above. Implement every operation listed in "
        "`operations`. Write the C source file(s) and a `Makefile` "
        "(target `agentfs`) into the source directory using your file tools."
    )
    return "\n".join(parts)
