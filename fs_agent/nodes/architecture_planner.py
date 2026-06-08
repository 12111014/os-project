import json
from pathlib import Path


def architecture_planner_node(state: dict):
    run_id = state["run_id"]
    workspace = Path("runs") / run_id

    plan = {
        "modules": [
            "main",
            "fuse_ops",
            "inode",
            "dir",
            "storage",
            "path",
            "tests",
        ],
        "data_model": {
            "inode": "in-memory inode table for MVP",
            "directory": "hash map from name to inode id",
            "file_data": "bytearray per file",
        },
        "fuse_operations": state["fs_ir"]["operations"],
        "limitations": [
            "no crash consistency",
            "no hardlink",
            "no xattr",
            "no journal",
        ],
    }

    architecture_path = workspace / "architecture.json"
    architecture_path.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "current_phase": "architecture_planned",
        "architecture_plan": plan,
        "architecture_path": str(architecture_path),
    }