from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecResult:
    code: int
    stdout: str
    stderr: str


@dataclass
class SandboxRef:
    run_id: str
    container_name: str
    host_workspace: Path
    container_workspace: str = "/workspace"


class SandboxManager:
    def __init__(self, image: str = "fs-agent:latest"):
        self.image = image

    def create(self, run_id: str, host_workspace: str | Path) -> SandboxRef:
        host_workspace = Path(host_workspace).resolve()
        host_workspace.mkdir(parents=True, exist_ok=True)

        container_name = f"fs-agent-run-{run_id}"

        cmd = [
            "docker", "run", "-d",
            "--init",
            "--name", container_name,
            "--device", "/dev/fuse",
            "--cap-add", "SYS_ADMIN",
            "--security-opt", "apparmor=unconfined",
            "--security-opt", "seccomp=unconfined",
            "-v", f"{host_workspace}:/workspace",
            self.image,
            "sleep", "infinity",
        ]

        subprocess.run(cmd, check=True, text=True, capture_output=True)

        return SandboxRef(
            run_id=run_id,
            container_name=container_name,
            host_workspace=host_workspace,
        )

    def upload(self, sandbox, source_dir, dest_dir) -> ExecResult:
        cmd = [
            "docker", "cp",
            source_dir,
            sandbox.container_name + f":{dest_dir}",
        ]

        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=False,
        )

        return ExecResult(proc.returncode, proc.stdout, proc.stderr)

    def exec(
        self,
        sandbox: SandboxRef,
        command: str,
        cwd: str = "/workspace",
        timeout: int = 120,
    ) -> ExecResult:
        cmd = [
            "docker", "exec",
            "-w", cwd,
            sandbox.container_name,
            "bash", "-lc", command,
        ]
        
        proc = None
        try:
            proc = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(124, "", f"[Sandbox] Command timed out after {timeout} seconds. 120 is the default timeout of sandbox.")

        return ExecResult(proc.returncode, proc.stdout, proc.stderr)

    def destroy(self, sandbox: SandboxRef) -> None:
        subprocess.run(
            ["docker", "rm", "-f", sandbox.container_name],
            text=True,
            capture_output=True,
            check=False,
        )


def sandbox_from_state(state: dict) -> SandboxRef:
    s = state["sandbox"]
    return SandboxRef(
        run_id=state["run_id"],
        container_name=s["container_name"],
        host_workspace=Path(s["host_workspace"]),
        container_workspace=s.get("container_workspace", "/workspace"),
    )
