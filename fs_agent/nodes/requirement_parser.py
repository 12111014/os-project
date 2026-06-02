import json
from pathlib import Path

from ..schemas.fs_ir import FilesystemIR


def requirement_parser_node(state: dict):
    run_id = state["run_id"]
    workspace = Path("runs") / run_id
    workspace.mkdir(parents=True, exist_ok=True)

    # MVP-0：先不用 LLM，生成默认 IR
    fs_ir = FilesystemIR(
        name="agentfs",
        storage={"type": "memory"},
        validation={
            "posix_smoke": True,
            "pytest": True,
            "fio": False,
            "filebench": False,
            "xfstests": False,
        },
    )

    fs_ir_path = workspace / "fs_ir.json"
    fs_ir_path.write_text(
        fs_ir.model_dump_json(indent=2),
        encoding="utf-8",
    )

    return {
        "current_phase": "requirement_parsed",
        "fs_ir": fs_ir.model_dump(),
        "fs_ir_path": str(fs_ir_path),
    }