"""Code generator node.

Generates the filesystem source with an LLM, grounded on the libfuse example
sources and a known-good template skeleton. If the LLM is unavailable
(no API key / dependency) or produces unusable output, it falls back to
copying the known-good template so the pipeline always has buildable code.
"""

import shutil
from pathlib import Path

from fs_agent.utils.llm import LLMUnavailable, generate_text
from fs_agent.utils.codegen import (
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_generated_files,
    validate_generated_files,
    fallback_template_dir,
)


def _copy_template(fs_ir: dict, source_root: Path) -> tuple[str, list[str]]:
    """Copy the fallback template into source_root. Returns (template_name, files)."""
    template_root = fallback_template_dir(fs_ir)
    if source_root.exists():
        shutil.rmtree(source_root)
    shutil.copytree(template_root, source_root)
    files = [str(p.relative_to(source_root)) for p in source_root.rglob("*") if p.is_file()]
    return template_root.name, files


def _write_generated(files: list[tuple[str, str]], source_root: Path) -> list[str]:
    """Write LLM-generated files under source_root. Returns written paths."""
    if source_root.exists():
        shutil.rmtree(source_root)
    source_root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for rel, content in files:
        # Keep everything inside source_root; ignore any path traversal.
        dest = (source_root / rel).resolve()
        if not str(dest).startswith(str(source_root.resolve())):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        written.append(rel)
    return written


def code_generator_node(state: dict):
    run_id = state["run_id"]
    workspace = Path("runs") / run_id
    source_root = workspace / "generated_fs"

    fs_ir = state.get("fs_ir", {})
    architecture_plan = state.get("architecture_plan", {})

    method = "llm"
    error = None
    files: list[tuple[str, str]] = []

    try:
        system = SYSTEM_PROMPT
        user = build_user_prompt(fs_ir, architecture_plan)
        raw = generate_text(system, user)
        files = parse_generated_files(raw)
        error = validate_generated_files(files)
        if error:
            raise ValueError(error)
        written = _write_generated(files, source_root)
        # Persist raw output for debugging / the report.
        (workspace / "codegen_raw.txt").write_text(raw, encoding="utf-8")
        summary = f"LLM generated {len(written)} file(s): {', '.join(written)}"
    except Exception as exc:  # LLMUnavailable, parse/validation errors, etc.
        method = "template_fallback"
        error = str(exc)
        template_name, written = _copy_template(fs_ir, source_root)
        summary = (
            f"LLM unavailable/invalid ({error}); copied known-good template "
            f"'{template_name}' ({len(written)} file(s))."
        )

    result_issues = []
    if method == "template_fallback":
        result_issues.append(
            {
                "type": "codegen_fallback",
                "summary": summary,
                "detail": error,
            }
        )

    return {
        "current_phase": "code_generated",
        "source_root": "/workspace/generated_fs",
        "build_dir": "/workspace/generated_fs/build",
        "fs_binary": "/workspace/generated_fs/build/agentfs",
        "artifacts": {
            **state.get("artifacts", {}),
            "source_root_host": str(source_root),
            "codegen_method": method,
        },
        "patches": [
            {
                "id": f"codegen-{method}",
                "summary": summary,
                "files_changed": written,
            }
        ],
        **({"issues": result_issues} if result_issues else {}),
    }
