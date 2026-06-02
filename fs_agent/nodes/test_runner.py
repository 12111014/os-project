from fs_agent.utils.sandbox_manager import SandboxManager, sandbox_from_state


def test_runner_node(state: dict):
    manager = SandboxManager()
    sandbox = sandbox_from_state(state)

    mountpoint = state["mountpoint"]
    log_path = "/workspace/logs/posix_smoke.log"
    script_path = "/workspace/run/test.sh"

    cmd = f"""
set -e

cat > {script_path} <<'EOF'
#!/bin/bash
echo hello > {mountpoint}/a.txt
test "$(cat {mountpoint}/a.txt)" = "hello"

mkdir {mountpoint}/d
echo world > {mountpoint}/d/b.txt
test "$(cat {mountpoint}/d/b.txt)" = "world"

mv {mountpoint}/d/b.txt {mountpoint}/c.txt
test "$(cat {mountpoint}/c.txt)" = "world"

rm {mountpoint}/a.txt
rm {mountpoint}/c.txt
rmdir {mountpoint}/d
EOF

chmod +x {script_path}
sh {script_path} > {log_path} 2>&1
"""

    result = manager.exec(
        sandbox,
        cmd,
        timeout=300,
    )

    if result.code == 0:
        return {
            "current_phase": "test_passed",
            "test_status": "passed",
            "logs": {**state.get("logs", {}), "posix_smoke": log_path},
        }

    return {
        "current_phase": "test_failed",
        "test_status": "failed",
        "logs": {**state.get("logs", {}), "posix_smoke": log_path},
        "issues": [
            {
                "type": "test_error",
                "summary": "POSIX smoke test failed.",
                "log_path": log_path,
            }
        ],
    }