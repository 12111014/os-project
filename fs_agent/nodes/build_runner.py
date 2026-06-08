"""Build runner node.

Compiles the generated/templated filesystem inside the sandbox and normalises
the produced binary to ``build/agentfs`` regardless of the Makefile's target
name. On failure it captures the tail of the build log into an issue so the
debugger has something to work with.
"""

from fs_agent.utils.sandbox_manager import SandboxManager, sandbox_from_state

LOG_TAIL_LINES = 60


def build_runner_node(state: dict):
    manager = SandboxManager()
    sandbox = sandbox_from_state(state)

    source_root = state["source_root"]
    log_path = "/workspace/logs/build.log"
    script_path = "/workspace/run/build.sh"

    # The build script is intentionally agnostic about the Makefile target and
    # the produced binary name: it runs `make`, then locates the freshest
    # executable and copies it to build/agentfs.
    cmd = f"""
set -e
mkdir -p /workspace/logs /workspace/run

cat > {script_path} <<'EOF'
#!/bin/bash
set -e
cd {source_root}
make clean || true
make -j

mkdir -p build
# Prefer a binary literally named agentfs, otherwise pick the newest
# executable file in the source root (excluding the build dir itself).
if [ -x ./agentfs ]; then
    BIN=./agentfs
else
    BIN=$(find . -maxdepth 1 -type f -perm -u+x ! -name '*.o' ! -name '*.sh' \
          -printf '%T@ %p\\n' | sort -rn | head -1 | cut -d' ' -f2-)
fi

if [ -z "$BIN" ] || [ ! -x "$BIN" ]; then
    echo "build_runner: no executable produced by make" >&2
    exit 2
fi

cp "$BIN" build/agentfs
echo "build_runner: installed $BIN -> build/agentfs"
EOF

chmod +x {script_path}
sh {script_path} > {log_path} 2>&1
"""

    result = manager.exec(sandbox, cmd, timeout=300)
    print(result.stdout, result.stderr)

    if result.code == 0:
        return {
            "current_phase": "build_passed",
            "build_status": "passed",
            "logs": {**state.get("logs", {}), "build": log_path},
        }

    # Pull the tail of the build log so the debugger / report has context.
    tail = _read_log_tail(manager, sandbox, log_path)

    return {
        "current_phase": "build_failed",
        "build_status": "failed",
        "logs": {**state.get("logs", {}), "build": log_path},
        "issues": [
            {
                "type": "build_error",
                "summary": "Build failed. See build.log.",
                "log_path": log_path,
                "log_tail": tail,
            }
        ],
    }


def _read_log_tail(manager, sandbox, log_path: str) -> str:
    try:
        res = manager.exec(
            sandbox, f"tail -n {LOG_TAIL_LINES} {log_path} 2>/dev/null", timeout=30
        )
        return res.stdout
    except Exception:  # best-effort; never fail the node on log reading
        return ""
