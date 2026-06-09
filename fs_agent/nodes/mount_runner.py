from fs_agent.utils.sandbox_manager import SandboxManager, sandbox_from_state
from fs_agent.agents.mount_runner_agent import MountRunnerAgent, MountAgentResult


def mount_runner_node(state: dict):
    agent = MountRunnerAgent(sandbox_from_state(state))
    result: MountAgentResult = agent.perform_task(state)

    print(f"""
================================
mount runner agent result: 
{result}
"""
)

    if result.mount_status == "mounted":
        return {
            "current_phase": "mounted",
            "mount_status": result.mount_status,
            "mountpoint": result.mountpoint,
            "fs_type": result.fs_type,
            "logs": {"fuse": result.log_path},
            "artifacts": {"fuse_pid": result.pid_path},
            # "issues": [issue.model_dump() for issue in result.issues],
        }
    else:
        return {
            "current_phase": "mount_failed",
            "mount_status": result.mount_status,
            "logs": {"fuse": result.log_path},
            "issues": [issue.model_dump() for issue in result.issues],
        }