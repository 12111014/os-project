from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from deepagents import create_deep_agent
from langchain.agents.structured_output import ToolStrategy
from pydantic import BaseModel, Field

from fs_agent.config import Config
from fs_agent.utils.sandbox_backend import SandboxBackend
from fs_agent.utils.sandbox_manager import SandboxRef


DEBUGGER_AGENT_PROMPT = """
You are the Debugger Agent for a generated FUSE filesystem pipeline. Your backend is running inside a Docker sandbox.
The pipeline contains code_generator, build_runner, mount_runner, test_runner, cleanup, etc.

Your job:
- Inspect the current pipeline state, source tree, build log, mount log, test logs, and recorded issues.
- Identify the smallest root cause that explains the failed build, mount, or test phase.
- Utilize debugging tools in sandbox environment for help.
- If the fix is clear and local to generated source files, patch the generated source using the provided sandbox tools.
- If the fix is not clear, do not guess. Return a diagnosis and concrete next inspection steps.
- Preserve the expected binary path, mountpoint, log paths, and generated source directory.
- Determine next pipeline phase after your debugging.
- Return only valid JSON.

Do not use host paths.
Do not use docker commands.
Use only the provided sandbox tools.
Avoid executing commands like "cd" since the sandbox backend cannot remember current working directory.
"""


DEBUG = Config().debug


@dataclass
class DebuggerContext:
    workspace: str
    fs_ir_path: str
    architecture_path: str
    source_dir: str
    build_dir: str
    fs_binary: str
    mountpoint: str
    current_phase: str
    build_status: str
    mount_status: str
    test_status: str
    logs: dict[str, Any]
    artifacts: dict[str, Any]
    issues: list[dict[str, Any]]
    patches: list[dict[str, Any]]
    debug_history: list[dict[str, Any]]


class DebugIssue(BaseModel):
    type: str
    summary: str
    phase: str = ""
    log_path: str = ""
    evidence: str = ""


class DebugPatch(BaseModel):
    id: str = ""
    summary: str
    files_changed: list[str] = Field(default_factory=list)
    rationale: str = ""


class DebuggerResult(BaseModel):
    debug_status: Literal["diagnosed", "patched", "failed"] = Field(
        description="Whether the debugger only diagnosed, applied a patch, or failed to find a useful diagnosis."
    )
    root_cause: str = Field(
        default="", description="Most likely root cause of the failing phase.")
    diagnosis: str = Field(
        default="", description="Human-readable debugging summary.")
    next_phase: Literal["build_runner", "mount_runner", "test_runner", "cleanup"] = Field(
        default="cleanup",
        description="Pipeline phase that should run next.",
    )
    issues: list[DebugIssue] = Field(default_factory=list)
    patches: list[DebugPatch] = Field(default_factory=list)


class DebuggerAgent:
    def __init__(self, sandbox: SandboxRef):
        cfg = Config()
        self.backend = SandboxBackend(sandbox)
        self.model = cfg.build_model("debugger")

        self.agent = create_deep_agent(
            model=self.model,
            backend=self.backend,
            system_prompt=DEBUGGER_AGENT_PROMPT,
            context_schema=DebuggerContext,
            response_format=ToolStrategy(DebuggerResult),
        )

    def _invoke(self, payload: dict[str, Any], context: DebuggerContext) -> DebuggerResult:
        if DEBUG:
            print("debugger agent invoking")
            from fs_agent.utils.stream_print import print_clean_deepagent_stream
            result = print_clean_deepagent_stream(
                self.agent, payload, context, True)
        else:
            result = self.agent.invoke(payload, context=context)
        return result["structured_response"]

    def perform_task(self, state: dict[str, Any], message: str = "") -> DebuggerResult:
        workspace = state.get("workspace")
        fs_ir_path = state.get("fs_ir_path")
        architecture_path = state.get("architecture_path")
        source_dir = state.get("source_root")
        build_dir = state.get("build_dir")
        fs_binary = state.get("fs_binary")
        mountpoint = state.get("mountpoint")
        logs = state.get("logs", {})
        artifacts = state.get("artifacts", {})
        issues = state.get("issues", [])
        patches = state.get("patches", [])
        debug_history = state.get("debug_hisory", [])

        context = DebuggerContext(
            workspace=workspace,
            fs_ir_path=fs_ir_path,
            architecture_path=architecture_path,
            source_dir=source_dir,
            build_dir=build_dir,
            fs_binary=fs_binary,
            mountpoint=mountpoint,
            current_phase=state.get("current_phase", ""),
            build_status=state.get("build_status", "not_started"),
            mount_status=state.get("mount_status", "not_started"),
            test_status=state.get("test_status", "not_started"),
            logs=logs,
            artifacts=artifacts,
            issues=issues,
            patches=patches,
            debug_history=debug_history,
        )

        instructions = (
            "Debug the generated FUSE filesystem pipeline.\n"
            f"- workspace: {workspace}\n"
            f"- source directory: {source_dir}\n"
            f"- build directory: {build_dir}\n"
            f"- filesystem binary: {fs_binary}\n"
            f"- mountpoint: {mountpoint}\n"
            f"- current phase: {context.current_phase}\n"
            f"- build status: {context.build_status}\n"
            f"- mount status: {context.mount_status}\n"
            f"- test status: {context.test_status}\n"
            f"- logs: {logs}\n"
            f"- artifacts: {artifacts}\n"
            f"- recorded issues: {issues}\n"
            f"- previous patches: {patches}\n"
            "Inspect only paths listed above unless a listed log/source file points to another sandbox path. "
            "If you edit files, edit generated source files under source directory and report every changed file."
        )

        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "Start the debugging task using the provided state and sandbox paths.",
                },
                {
                    "role": "user",
                    "content": instructions + (f"\n\n{message}" if message else ""),
                },
            ]
        }
        return self._invoke(payload, context)
