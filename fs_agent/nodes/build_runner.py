from fs_agent.utils.sandbox_manager import SandboxManager, sandbox_from_state


def build_runner_node(state: dict):
    manager = SandboxManager()
    sandbox = sandbox_from_state(state)

    log_path = "/workspace/logs/build.log"
    script_path = "/workspace/run/build.sh"

    cmd = f"""
set -e
mkdir -p /workspace/logs /workspace/run

cat > {script_path} <<'EOF'
#!/bin/bash
cd {state["source_root"]}
make clean || true
make -j
mkdir -p build
mv passthrough_ll build/agentfs
EOF

chmod +x {script_path}

sh {script_path} > {log_path} 2>&1
"""

    result = manager.exec(
        sandbox,
        cmd,
        timeout=300,
    )
    
    print(result.stdout, result.stderr)

    if result.code == 0:
        return {
            "current_phase": "build_passed",
            "build_status": "passed",
            "logs": {**state.get("logs", {}), "build": log_path},
        }

    return {
        "current_phase": "build_failed",
        "build_status": "failed",
        "logs": {**state.get("logs", {}), "build": log_path},
        "issues": [
            {
                "type": "build_error",
                "summary": "Build failed. See build.log.",
                "log_path": log_path,
            }
        ],
    }