from dataclasses import dataclass
from typing import Literal
from deepagents import create_deep_agent
from langchain.agents.structured_output import ToolStrategy
from pathlib import Path

from pydantic import BaseModel, Field

from fs_agent.config import Config
from fs_agent.utils.sandbox_backend import SandboxBackend
from fs_agent.utils.sandbox_manager import SandboxRef

BUILD_RUNNER_AGENT_PROMPT = """
You are the Build Agent for a generated FUSE filesystem. You run inside a Docker
sandbox and your tools (`execute`, `read_file`, `ls`, ...) operate inside it.

Your job:
- Inspect the generated source directory.
- Compile the filesystem with `make` inside the sandbox.
- The Makefile target and the produced binary name may vary: after building,
  locate the freshest executable and copy it to `<build_dir>/agentfs` so the
  rest of the pipeline always finds the binary at a known path.
- Capture all build output (stdout and stderr) into the build log path given
  to you.
- Verify the `agentfs` binary exists and is executable.
- Return only the structured JSON result.

On failure, include a short diagnosis and the tail of the build log so the
debugger has something to work with.

Do not use host paths. Do not use docker commands. Use only the provided
sandbox tools.
"""


DEBUG = Config().debug


@dataclass
class BuildRunnerContext:
    source_dir: str
    build_dir: str
    fs_binary: str
    log_path: str


class BuildIssue(BaseModel):
    type: str
    summary: str
    log_path: str = ""
    log_tail: str = ""


class BuildRunnerResult(BaseModel):
    build_status: Literal["passed", "failed"] = Field(
        description="Whether the filesystem was compiled successfully."
    )

    binary_path: str = Field(
        default="/workspace/generated_fs/build/agentfs",
        description="Path of the normalised `agentfs` binary inside the sandbox.",
    )

    log_path: str = Field(
        default="/workspace/logs/build.log",
        description="Path of the build stdout/stderr log.",
    )

    diagnosis: str = Field(
        default="",
        description="Human-readable diagnosis of the build result.",
    )

    log_tail: str = Field(
        default="",
        description="Tail of the build log, useful when the build failed.",
    )

    issues: list[BuildIssue] = Field(
        default_factory=list,
        description="Non-fatal or fatal issues discovered during the build.",
    )


class BuildRunnerAgent:
    def __init__(self, sandbox: SandboxRef):
        cfg = Config()
        self.backend = SandboxBackend(sandbox)
        self.model = cfg.build_model("build_runner")

        self.agent = create_deep_agent(
            model=self.model,
            backend=self.backend,
            system_prompt=BUILD_RUNNER_AGENT_PROMPT,
            context_schema=BuildRunnerContext,
            response_format=ToolStrategy(BuildRunnerResult),
        )

    def _invoke(self, payload, context):
        if DEBUG:
            print("build runner agent invoking")
            from fs_agent.utils.stream_print import print_clean_deepagent_stream
            result = print_clean_deepagent_stream(self.agent, payload, context, True)
        else:
            result = self.agent.invoke(payload, context=context)
        return result["structured_response"]

    def perform_task(self, state, message=""):
        source_dir = state["source_root"]
        build_dir = state["build_dir"]
        fs_binary = state["fs_binary"]
        log_path = str(Path(state["workspace"]) / "logs" / "build.log")

        instructions = (
            f"Build the FUSE filesystem.\n"
            f"- source directory: {source_dir}\n"
            f"- build directory: {build_dir}\n"
            f"- normalise the produced binary to: {fs_binary}\n"
            f"- write the build log to: {log_path}\n"
        )

        payload = {
            "messages": [{
                "role": "system",
                "content": "Start to perform the build task using the state provided."
            }, {
                "role": "user",
                "content": instructions + (f"\n{message}" if message else "")
            }]
        }
        context = BuildRunnerContext(
            source_dir=source_dir,
            build_dir=build_dir,
            fs_binary=fs_binary,
            log_path=log_path,
        )
        return self._invoke(payload, context=context)
