import shutil
from pathlib import Path


def code_generator_node(state: dict):
    run_id = state["run_id"]

    workspace = Path("runs") / run_id
    source_root = workspace / "generated_fs"

    template_root = Path("templates") / "passthrough_ll"

    if source_root.exists():
        shutil.rmtree(source_root)

    shutil.copytree(template_root, source_root)

    return {
        "current_phase": "code_generated",
        "source_root": "/workspace/generated_fs",
        "build_dir": "/workspace/generated_fs/build",
        "fs_binary": "/workspace/generated_fs/build/agentfs",
        "artifacts": {
            "source_root_host": str(source_root),
        },
        "patches": [
            {
                "id": "initial-template",
                "summary": "Copied initial FUSE memfs C template.",
                "files_changed": [],
            }
        ],
    }