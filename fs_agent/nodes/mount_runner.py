from fs_agent.utils.sandbox_manager import SandboxManager, sandbox_from_state


def mount_runner_node(state: dict):
    manager = SandboxManager()
    sandbox = sandbox_from_state(state)

    mountpoint = state["mountpoint"]
    fuse_log = "/workspace/logs/fuse.log"
    pid_path = "/workspace/run/fuse.pid"

    cmd = f"""
set -e
mkdir -p /workspace/logs /workspace/run {mountpoint}
nohup {state["fs_binary"]} -f {mountpoint} > {fuse_log} 2>&1 &
echo $! > {pid_path}
sleep 1
mountpoint -q {mountpoint}
"""

    result = manager.exec(sandbox, cmd, timeout=30)

    if result.code == 0:
        return {
            "current_phase": "mounted",
            "mount_status": "mounted",
            "logs": {**state.get("logs", {}), "fuse": fuse_log},
            "artifacts": {**state.get("artifacts", {}), "fuse_pid": pid_path},
        }

    return {
        "current_phase": "mount_failed",
        "mount_status": "failed",
        "logs": {**state.get("logs", {}), "fuse": fuse_log},
        "issues": [
            {
                "type": "mount_error",
                "summary": "FUSE mount failed.",
                "log_path": fuse_log,
            }
        ],
    }