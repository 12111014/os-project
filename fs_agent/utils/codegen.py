"""Helpers for the code generator node.

Kept separate from the node so the prompt-building and output-parsing logic
can be unit-tested without LangGraph or a live LLM.
"""

from __future__ import annotations

import re
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
    """Pick the known-good template directory used when the LLM is unavailable."""
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


SYSTEM_PROMPT = """\
You are an expert C systems programmer specialising in FUSE filesystems.
You generate small, correct, self-contained user-space filesystems that build
against libfuse3 using the high-level API (#include <fuse.h>, struct
fuse_operations, fuse_main).

Hard requirements:
- Use FUSE_USE_VERSION 31 and the high-level API only.
- The program's binary, when built, must be named `agentfs`.
- It must mount in the foreground with: ./agentfs -f <mountpoint>
- Match the exact callback signatures used by the reference examples for this
  libfuse version (e.g. getattr/chmod/truncate take a `struct fuse_file_info *`,
  readdir takes `enum fuse_readdir_flags`, rename takes `unsigned int flags`).
- Be thread-safe (libfuse high-level API is multithreaded by default): guard
  shared state with a mutex.
- Return correct negative errno values on failure. No memory corruption.
- Do not invent APIs. If unsure, mirror the reference code.

Output format — emit ONLY files, each delimited EXACTLY like this:
=== FILE: <relative/path> ===
<verbatim file content>
=== END FILE ===

You MUST output at least a C source file and a `Makefile`. The Makefile must
produce a binary named `agentfs` and use:
    $(shell pkg-config --cflags fuse3)  and  $(shell pkg-config --libs fuse3)
Do not output any prose outside the FILE blocks.
"""


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
        "`operations`. Emit the C source file(s) and a `Makefile` "
        "(target `agentfs`) using the required FILE block format."
    )
    return "\n".join(parts)


# Matches:  === FILE: path ===\n<content>\n=== END FILE ===
_FILE_BLOCK_RE = re.compile(
    r"===\s*FILE:\s*(?P<path>.+?)\s*===\n(?P<body>.*?)\n===\s*END FILE\s*===",
    re.DOTALL,
)


def parse_generated_files(text: str) -> list[tuple[str, str]]:
    """Extract (relative_path, content) pairs from the model output.

    Returns an empty list if the output does not contain any FILE blocks.
    """
    files: list[tuple[str, str]] = []
    for m in _FILE_BLOCK_RE.finditer(text):
        rel = m.group("path").strip().lstrip("/")
        body = m.group("body")
        # Strip an optional ``` fence the model may add inside the block.
        body = _strip_code_fence(body)
        if rel:
            files.append((rel, body))
    return files


def _strip_code_fence(body: str) -> str:
    lines = body.split("\n")
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
    return "\n".join(lines)


def validate_generated_files(files: list[tuple[str, str]]) -> str | None:
    """Return an error string if the file set looks unusable, else None."""
    if not files:
        return "no FILE blocks found in model output"
    names = [Path(p).name for p, _ in files]
    has_c = any(n.endswith(".c") for n in names)
    has_make = any(n == "Makefile" for n in names)
    if not has_c:
        return "no .c source file in generated output"
    if not has_make:
        return "no Makefile in generated output"
    for path, content in files:
        if not content.strip():
            return f"generated file {path} is empty"
    return None
