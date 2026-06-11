from fs_agent.utils.sandbox_manager import SandboxManager, sandbox_from_state


def cleanup_node(state: dict):
    manager = SandboxManager()
    sandbox = sandbox_from_state(state)

    mountpoint = state.get("mountpoint", "/mnt/agentfs")
    pid_path = state.get("artifacts", {}).get("fuse_pid", "/workspace/run/fuse.pid")

    cmd = f"""
set +e
if mountpoint -q {mountpoint}; then
  fusermount3 -u {mountpoint} || fusermount -u {mountpoint} || umount -l {mountpoint}
fi

if [ -f {pid_path} ]; then
  kill $(cat {pid_path}) 2>/dev/null || true
fi
"""

    manager.exec(sandbox, cmd, timeout=30)
    
    manager.destroy(sandbox)

    return {
        "mount_status": "cleaned",
        "current_phase": "cleaned",
    }