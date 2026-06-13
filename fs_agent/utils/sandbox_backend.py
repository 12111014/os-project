import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from deepagents.backends.protocol import FileDownloadResponse, FileUploadResponse, ExecuteResponse

from deepagents.backends.sandbox import BaseSandbox
from fs_agent.utils.sandbox_manager import SandboxManager, SandboxRef


class SandboxBackend(BaseSandbox):
    @property
    def id(self) -> str:
        return self.sandbox.run_id

    def __init__(self, sandbox: SandboxRef):
        self.sandbox = sandbox
        self.manager = SandboxManager()

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        result = self.manager.exec(self.sandbox, command, timeout=120 if not timeout or timeout > 120 else timeout)
        return ExecuteResponse(output=result.stdout + result.stderr, exit_code=result.code, truncated=False)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for container_path, content in files:
            tmp_dir = tempfile.mkdtemp(prefix="deepagents-upload-")
            try:
                tmp_file = Path(tmp_dir) / "payload"
                tmp_file.write_bytes(content)

                parent = os.path.dirname(container_path) or "/"
                mkdir = self.execute(f"mkdir -p {shlex.quote(parent)}", timeout=20)
                if mkdir.exit_code != 0:
                    responses.append(
                        FileUploadResponse(path=container_path, error="permission_denied")
                    )
                    continue
                cp = subprocess.run(
                    [
                        "docker",
                        "cp",
                        str(tmp_file),
                        f"{self.sandbox.container_name}:{container_path}",
                    ],
                    text=True,
                    capture_output=True,
                )
                if cp.returncode == 0:
                    responses.append(FileUploadResponse(path=container_path, error=None))
                else:
                    responses.append(
                        FileUploadResponse(
                            path=container_path,
                            error=cp.stderr.strip() or "upload_failed",
                        )
                    )

            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []

        for container_path in paths:
            tmp_dir = tempfile.mkdtemp(prefix="deepagents-download-")
            try:
                local_path = Path(tmp_dir) / "payload"

                cp = subprocess.run(
                    [
                        "docker",
                        "cp",
                        f"{self.sandbox.container_name}:{container_path}",
                        str(local_path),
                    ],
                    text=True,
                    capture_output=True,
                )

                if cp.returncode != 0:
                    responses.append(
                        FileDownloadResponse(
                            path=container_path,
                            content=None,
                            error="file_not_found",
                        )
                    )
                    continue

                if local_path.is_dir():
                    responses.append(
                        FileDownloadResponse(
                            path=container_path,
                            content=None,
                            error="is_directory",
                        )
                    )
                    continue

                responses.append(
                    FileDownloadResponse(
                        path=container_path,
                        content=local_path.read_bytes(),
                        error=None,
                    )
                )

            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        return responses
