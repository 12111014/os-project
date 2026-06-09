from dataclasses import dataclass
from typing import Literal
from deepagents import create_deep_agent, DeepAgentState
from langchain.agents.structured_output import ToolStrategy
from pathlib import Path

from pydantic import BaseModel, Field

from fs_agent.config import Config
from fs_agent.utils.sandbox_backend import SandboxBackend
from fs_agent.utils.sandbox_manager import sandbox_from_state, SandboxRef

MOUNT_RUNNER_AGENT_PROMPT = """
You are the Mount Agent for a generated FUSE filesystem. Your backend is running inside a Docker sandbox.

Your job:
- Inspect the built FUSE binary and source code.
- Determine the correct mount command.
- Mount the filesystem inside the Docker sandbox.
- Write the FUSE filesystem logs into specified path.
- Save the FUSE filesystem pid into specified path.
- Check mountpoint.
- Return only valid JSON.

Do not use host paths.
Do not use docker commands.
Use only the provided sandbox tools.
Avoid executing commands like "cd" since the sandbox backend cannot remember current working directory.
    """


DEBUG = Config().debug


@dataclass
class MountRunnerContext:
    workspace: str
    source_dir: str
    mountpoint: str
    log_path: str
    pid_path: str


class MountAttempt(BaseModel):
    command: str = Field(
        description="The mount command attempted by the agent.")
    exit_code: int | None = Field(
        default=None,
        description="Exit code of the command if available.",
    )
    observation: str = Field(
        default="",
        description="Short observation from command output, logs, or mount check.",
    )


class MountIssue(BaseModel):
    type: str
    summary: str


class MountAgentResult(BaseModel):
    mount_status: Literal["mounted", "failed"] = Field(
        description="Whether the FUSE filesystem was mounted successfully."
    )

    mount_command: str = Field(
        default="",
        description="Final command used to mount the filesystem.",
    )

    mountpoint: str = Field(
        default="/mnt/agentfs",
        description="FUSE mountpoint inside the sandbox.",
    )

    pid_path: str = Field(
        default="/workspace/run/fuse.pid",
        description="Path of the file storing the FUSE daemon PID.",
    )

    log_path: str = Field(
        default="/workspace/logs/fuse.log",
        description="Path of the FUSE stdout/stderr log.",
    )

    fs_type: str | None = Field(
        default=None,
        description="Filesystem type reported by mount/findmnt, e.g. fuse.agentfs.",
    )

    diagnosis: str = Field(
        default="",
        description="Human-readable diagnosis of the mount result.",
    )

    attempts: list[MountAttempt] = Field(
        default_factory=list,
        description="Mount attempts made by the agent.",
    )

    issues: list[MountIssue] = Field(
        default_factory=list,
        description="Non-fatal or fatal issues discovered during mounting.",
    )


class MountRunnerAgent:
    def __init__(self, sandbox: SandboxRef):
        cfg = Config()
        self.backend = SandboxBackend(sandbox)
        self.model = cfg.build_model("mount_runner")

        self.agent = create_deep_agent(
            model=self.model,
            backend=self.backend,
            system_prompt=MOUNT_RUNNER_AGENT_PROMPT,
            context_schema=MountRunnerContext,
            response_format=ToolStrategy(MountAgentResult),
        )

    def _invoke(self, payload, context):
        if DEBUG:
            print("mount runner agent invoking")
            from fs_agent.utils.stream_print import print_clean_deepagent_stream
            result = print_clean_deepagent_stream(self.agent, payload, context, True)
        else:
            result = self.agent.invoke(payload, context=context)
        return result["structured_response"]

    def perform_task(self, state, message=""):
        payload = {
            "messages": [{
                "role": "system",
                "content": "Start to perform the mount task using the state provided."
            }, {
                "role": "user",
                "content": message
            }]
        }
        context = MountRunnerContext(
            workspace=state["workspace"],
            source_dir=state["source_root"],
            mountpoint=state["mountpoint"],
            log_path=str(
                Path(state["workspace"]) / "logs" / "fuse.log"),
            pid_path=str(Path(state["workspace"]) / "run" / "fuse.pid"))
        return self._invoke(payload, context=context)
