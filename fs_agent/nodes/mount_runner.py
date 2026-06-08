from fs_agent.schemas.agent_outputs import MountAgentResult
from fs_agent.utils.sandbox_manager import SandboxManager, sandbox_from_state
from fs_agent.agents.mount_runner_agent import MountRunnerAgent


def mount_runner_node(state: dict):
    #     manager = SandboxManager()
    #     sandbox = sandbox_from_state(state)

    #     mountpoint = state["mountpoint"]
    #     fuse_log = "/workspace/logs/fuse.log"
    #     pid_path = "/workspace/run/fuse.pid"

    #     cmd = f"""
    # set -e
    # mkdir -p /workspace/logs /workspace/run {mountpoint}
    # nohup {state["fs_binary"]} -f {mountpoint} > {fuse_log} 2>&1 &
    # echo $! > {pid_path}
    # sleep 1
    # mountpoint -q {mountpoint}
    # """

    agent = MountRunnerAgent(sandbox_from_state(state))
    result: MountAgentResult = agent.perform_task(state)

    print("mount agent result: ", result)

    if result.mount_status == "failed":
        return {
            "current_phase": "mount_failed",
            "mount_status": result.mount_status,
            "logs": {**state.get("logs", {}), "fuse": result.log_path},
            "issues": result.issues
        }

    return {
        "current_phase": "mounted",
        "mount_status": result.mount_status,
        "mountpoint": result.mountpoint,
        "filesystem_type": result.filesystem_type,
        "logs": {**state.get("logs", {}), "fuse": result.log_path},
        "artifacts": {**state.get("artifacts", {}), "fuse_pid": result.pid_path},
    }