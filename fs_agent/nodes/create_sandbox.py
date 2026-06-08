from pathlib import Path
from fs_agent.utils.sandbox_manager import SandboxManager


def create_sandbox_node(state: dict):
    run_id = state["run_id"]
    host_workspace = Path("runs") / run_id
    host_workspace.mkdir(parents=True, exist_ok=True)

    manager = SandboxManager("fs-agent:latest")
    sandbox = manager.create(run_id, host_workspace)

    return {
        "current_phase": "sandbox_created",
        "sandbox": {
            "container_name": sandbox.container_name,
            "host_workspace": str(sandbox.host_workspace),
            "container_workspace": sandbox.container_workspace,
        },
        "workspace": "/workspace",
        "source_root": "/workspace/generated_fs",
        "build_dir": "/workspace/generated_fs/build",
        "fs_binary": "/workspace/generated_fs/build/agentfs",
        "mountpoint": "/mnt/agentfs",
        "build_status": "not_started",
        "mount_status": "not_started",
        "test_status": "not_started",
        "retry_count": 0,
        "max_retries": state.get("max_retries", 2),
        "logs": {},
        "artifacts": {},
    }