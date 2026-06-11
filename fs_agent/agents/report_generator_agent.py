from dataclasses import dataclass
from typing import Any

from deepagents import create_deep_agent
from langchain.agents.structured_output import ToolStrategy
from pydantic import BaseModel, Field

from fs_agent.config import Config
from fs_agent.utils.sandbox_backend import SandboxBackend
from fs_agent.utils.sandbox_manager import SandboxRef
from fs_agent.utils.system_prompt import build_system_prompt


REPORT_GENERATOR_AGENT_PROMPT = """
You are the Report Generator Agent for a generated FUSE filesystem pipeline. Your backend is running inside a Docker sandbox.

Your job:
- Read the final pipeline state supplied in the user message.
- Inspect logs and artifacts inside workspace.
- Write one detailed Markdown report to the exact report path supplied by the user.
- Summarize the request, pipeline statuses, generated artifacts, issues, patches, logs, and final outcome.
- If the run failed, make the failure reason and next manual action clear.
- Return only valid JSON.

Do not use host paths.
Do not use docker commands.
Use only the provided sandbox tools.
Avoid executing commands like "cd" since the sandbox backend cannot remember current working directory.
"""


DEBUG = Config().debug


@dataclass
class ReportGeneratorContext:
    workspace: str
    report_path: str
    run_id: str
    user_request: str
    current_phase: str
    build_status: str
    mount_status: str
    test_status: str
    debug_status: str
    source_root: str
    build_dir: str
    fs_binary: str
    logs: dict[str, Any]
    artifacts: dict[str, Any]
    issues: list[dict[str, Any]]
    patches: list[dict[str, Any]]
    fs_ir: dict[str, Any]
    architecture_plan: dict[str, Any]
    retry_count: int
    max_retries: int


class ReportSection(BaseModel):
    title: str
    summary: str


class ReportGeneratorResult(BaseModel):
    final_report_path: str = Field(
        default="/workspace/report.md",
        description="Absolute sandbox path of the Markdown report written by the agent.",
    )
    final_summary: str = Field(default="", description="Short final run summary.")
    outcome: str = Field(default="", description="Human-readable final outcome of the pipeline.")
    sections: list[ReportSection] = Field(default_factory=list)
    issues_count: int = 0
    patches_count: int = 0


class ReportGeneratorAgent:
    def __init__(self, sandbox: SandboxRef):
        cfg = Config()
        self.backend = SandboxBackend(sandbox)
        self.model = cfg.build_model("report_generator")

        self.agent = create_deep_agent(
            model=self.model,
            backend=self.backend,
            system_prompt=build_system_prompt(REPORT_GENERATOR_AGENT_PROMPT),
            context_schema=ReportGeneratorContext,
            response_format=ToolStrategy(ReportGeneratorResult),
        )

    def _invoke(self, payload: dict[str, Any], context: ReportGeneratorContext) -> ReportGeneratorResult:
        if DEBUG:
            print("report generator agent invoking")
            from fs_agent.utils.stream_print import print_clean_deepagent_stream
            result = print_clean_deepagent_stream(self.agent, payload, context, True)
        else:
            result = self.agent.invoke(payload, context=context)
        return result["structured_response"]

    def perform_task(self, state: dict[str, Any], message: str = "") -> ReportGeneratorResult:
        workspace = state.get("workspace")
        report_path = state.get("final_report_path")
        logs = state.get("logs")
        artifacts = state.get("artifacts")
        issues = state.get("issues")
        patches = state.get("patches")
        fs_ir = state.get("fs_ir")
        architecture_plan = state.get("architecture_plan")
        retry_count = state.get("retry_count")
        max_retries = state.get("max_retries")

        context = ReportGeneratorContext(
            workspace=workspace,
            report_path=report_path,
            run_id=state.get("run_id"),
            user_request=state.get("user_request"),
            current_phase=state.get("current_phase"),
            build_status=state.get("build_status"),
            mount_status=state.get("mount_status"),
            test_status=state.get("test_status"),
            debug_status=state.get("debug_status"),
            source_root=state.get("source_root"),
            build_dir=state.get("build_dir"),
            fs_binary=state.get("build_dir"),
            logs=logs,
            artifacts=artifacts,
            issues=issues,
            patches=patches,
            fs_ir=fs_ir,
            architecture_plan=architecture_plan,
            retry_count=retry_count,
            max_retries=max_retries,
        )

        instructions = (
            "Generate the final filesystem pipeline report.\n"
            f"- run id: {context.run_id}\n"
            f"- user request: {context.user_request}\n"
            f"- workspace: {workspace}\n"
            f"- write report to exactly: {report_path}\n"
            f"- current phase: {context.current_phase}\n"
            f"- build status: {context.build_status}\n"
            f"- mount status: {context.mount_status}\n"
            f"- test status: {context.test_status}\n"
            f"- debug status: {context.debug_status}\n"
            f"- source root: {context.source_root}\n"
            f"- build dir: {context.build_dir}\n"
            f"- binary path: {context.fs_binary}\n"
            f"- logs: {logs}\n"
            f"- artifacts: {artifacts}\n"
            f"- issues: {issues}\n"
            f"- patches: {patches}\n"
            f"- filesystem IR: {fs_ir}\n"
            f"- architecture plan: {architecture_plan}\n"
            f"- retry count: {retry_count}\n"
            f"- max retries: {max_retries}\n"
            "The report must be Markdown and must include enough detail for a user to understand what succeeded, what failed, and where logs/artifacts are stored."
        )

        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "Start the final report generation task using the supplied state and report path.",
                },
                {
                    "role": "user",
                    "content": instructions + (f"\n\n{message}" if message else ""),
                },
            ]
        }
        return self._invoke(payload, context)
