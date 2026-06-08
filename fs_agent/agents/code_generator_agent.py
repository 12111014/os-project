from dataclasses import dataclass
from typing import Literal
from deepagents import create_deep_agent
from langchain.agents.structured_output import ToolStrategy

from pydantic import BaseModel, Field

from fs_agent.config import Config
from fs_agent.utils.sandbox_backend import SandboxBackend
from fs_agent.utils.sandbox_manager import SandboxRef
from fs_agent.utils.codegen import build_user_prompt

CODE_GENERATOR_AGENT_PROMPT = """
You are the Code Generator Agent for a FUSE filesystem. You run inside a Docker
sandbox and your file tools write directly into that sandbox.

Your job:
- Read the filesystem specification, architecture plan, the known-good skeleton
  and the libfuse reference examples provided in the user message.
- Generate a complete, buildable user-space FUSE filesystem and write every
  file into the source directory given to you using the `write_file` tool.
- You MUST produce at least one C source file and a `Makefile`.

Hard requirements for the generated code:
- Use FUSE_USE_VERSION 31 and the high-level API only (#include <fuse.h>,
  struct fuse_operations, fuse_main).
- The built binary must be named `agentfs` and mount in the foreground with:
  ./agentfs -f <mountpoint>
- Match the exact callback signatures used by the reference examples for this
  libfuse version (e.g. getattr/chmod/truncate take a `struct fuse_file_info *`,
  readdir takes `enum fuse_readdir_flags`, rename takes `unsigned int flags`).
- Be thread-safe: guard shared state with a mutex.
- Return correct negative errno values on failure. No memory corruption.
- Do not invent APIs. If unsure, mirror the reference code / skeleton.
- The Makefile must build the `agentfs` target using
  `$(shell pkg-config --cflags fuse3)` and `$(shell pkg-config --libs fuse3)`.

Prefer adapting the known-good skeleton over writing from scratch.

Write the files with `write_file` (one call per file) using paths relative to
the source directory you are given. Do not print file contents in chat. When
done, return only the structured JSON result describing what you wrote.
"""


DEBUG = Config().debug


@dataclass
class CodeGeneratorContext:
    source_dir: str
    build_dir: str
    fs_binary: str


class CodeGenIssue(BaseModel):
    type: str
    summary: str


class CodeGeneratorResult(BaseModel):
    status: Literal["generated", "failed"] = Field(
        description="Whether buildable source code was successfully generated."
    )

    method: str = Field(
        default="agent",
        description="How the code was produced, e.g. 'agent'.",
    )

    source_root: str = Field(
        default="/workspace/generated_fs",
        description="Directory inside the sandbox where the source was written.",
    )

    files: list[str] = Field(
        default_factory=list,
        description="Paths (relative to source_root) of files written by the agent.",
    )

    summary: str = Field(
        default="",
        description="Human-readable summary of what was generated.",
    )

    issues: list[CodeGenIssue] = Field(
        default_factory=list,
        description="Non-fatal or fatal issues discovered during generation.",
    )


class CodeGeneratorAgent:
    def __init__(self, sandbox: SandboxRef):
        cfg = Config()
        self.backend = SandboxBackend(sandbox)
        self.model = cfg.build_model("code_generator")

        self.agent = create_deep_agent(
            model=self.model,
            backend=self.backend,
            system_prompt=CODE_GENERATOR_AGENT_PROMPT,
            context_schema=CodeGeneratorContext,
            response_format=ToolStrategy(CodeGeneratorResult),
        )

    def _invoke(self, payload, context):
        if DEBUG:
            print("code generator agent invoking")
            from fs_agent.utils.stream_print import print_clean_deepagent_stream
            result = print_clean_deepagent_stream(self.agent, payload, context, True)
        else:
            result = self.agent.invoke(payload, context=context)
        return result["structured_response"]

    def perform_task(self, state, message=""):
        fs_ir = state.get("fs_ir", {})
        architecture_plan = state.get("architecture_plan", {})
        source_dir = state["source_root"]

        grounding = build_user_prompt(fs_ir, architecture_plan)
        instructions = (
            f"Write all generated files into the source directory: {source_dir}\n"
            f"Use paths relative to that directory (e.g. the C source and `Makefile`).\n\n"
            f"{grounding}"
        )

        payload = {
            "messages": [{
                "role": "system",
                "content": "Start to generate the filesystem source using the spec provided."
            }, {
                "role": "user",
                "content": instructions + (f"\n\n{message}" if message else "")
            }]
        }
        context = CodeGeneratorContext(
            source_dir=source_dir,
            build_dir=state["build_dir"],
            fs_binary=state["fs_binary"],
        )
        return self._invoke(payload, context=context)
