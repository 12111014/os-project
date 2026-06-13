from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from deepagents import create_deep_agent
from langchain.agents.structured_output import ToolStrategy
from pydantic import BaseModel, Field

from fs_agent.config import Config
from fs_agent.utils.sandbox_backend import SandboxBackend
from fs_agent.utils.sandbox_manager import SandboxRef
from fs_agent.utils.system_prompt import build_system_prompt


TEST_RUNNER_AGENT_PROMPT = """
You are the Test Agent for a generated FUSE filesystem. Your backend is running inside a Docker sandbox.
The filesystem under test is already mounted. You are provided with a test policy, filesystem IR, directory specifications and uploaded deterministic test templates.

Your job:
- Inspect the mounted FUSE filesystem before testing.
- Run only policy-enabled suites unless an extra diagnostic check is needed to explain a failure.
- Prefer the uploaded templates inside provided test_template_dir over inventing new tests, but if template tests are not enough to fs_ir, you should modify templates or conduct additional tests.
- Based on fs_ir, develop new and necessary tests not in test templates.
- Copy or render every script/workload you run inside provided test_run_dir.
- Write test logs inside provided test_log_dir.
- Separate correctness failures from benchmark degradation.
- Do not try to fix the filesystem by yourself if you encountered errors, turn to debugger agent. 
- Record concise issues with log paths for every failed or timed-out case.
- Write a detailed test report markdown file inside provided test_result_dir.
- Return only valid JSON.

Required ordering:
1. preflight mount checks.
2. correctness tests.
3. short stress tests if enabled.
4. quick benchmark tests if enabled.

Do not edit source files. 
Do not use host paths.
Do not use docker commands.
Use only the provided sandbox tools.
Avoid executing commands like "cd" since the sandbox backend cannot remember current working directory.
"""

DEBUG = Config().debug


@dataclass
class TestRunnerContext:
    workspace: str
    mountpoint: str
    fs_binary: str
    fs_type: str
    fuse_log_path: str
    fuse_pid_path: str
    fs_ir: dict[str, Any]
    test_policy: dict[str, Any]
    test_template_dir: str
    test_run_dir: str
    test_log_dir: str
    test_result_dir: str
    retry_count: int


class TestCaseResult(BaseModel):
    name: str
    suite: str
    status: Literal["passed", "failed", "skipped", "timeout"]
    command: str = ""
    exit_code: int | None = None
    log_path: str = ""
    duration_sec: float | None = None
    summary: str = ""


class BenchmarkMetric(BaseModel):
    name: str
    value: float
    unit: str
    suite: str = ""
    baseline: str | None = None
    ratio: float | None = None


class TestIssue(BaseModel):
    type: str
    summary: str
    log_path: str = ""
    case_name: str = ""


class TestAgentResult(BaseModel):
    test_status: Literal["passed", "failed", "degraded"] = Field(
        description="Overall test result. Use degraded only for benchmark regressions without correctness failures."
    )
    suites_run: list[str] = Field(default_factory=list)
    cases: list[TestCaseResult] = Field(default_factory=list)
    metrics: list[BenchmarkMetric] = Field(default_factory=list)
    logs: dict[str, str] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    issues: list[TestIssue] = Field(default_factory=list)


class TestRunnerAgent:
    def __init__(self, sandbox: SandboxRef):
        cfg = Config()
        self.backend = SandboxBackend(sandbox)
        self.model = cfg.build_model("test_runner")

        self.agent = create_deep_agent(
            model=self.model,
            backend=self.backend,
            system_prompt=build_system_prompt(TEST_RUNNER_AGENT_PROMPT),
            context_schema=TestRunnerContext,
            response_format=ToolStrategy(TestAgentResult),
        )

    def _invoke(self, payload: dict[str, Any], context: TestRunnerContext) -> TestAgentResult:
        if DEBUG:
            print("test runner agent invoking")
            from fs_agent.utils.stream_print import print_clean_deepagent_stream
            result = print_clean_deepagent_stream(
                self.agent, payload, context, True)
        else:
            result = self.agent.invoke(payload, context=context)
        return result["structured_response"]

    def perform_task(self, state: dict[str, Any], message: str = "") -> TestAgentResult:
        test_template_dir = str(
            Path(state.get("template_dir", "/workspace/templates")) / "tests")
        test_run_dir = str(
            Path(state.get("workspace", "/workspace")) / "run" / "tests" / "[retry_count]")
        test_log_dir = str(
            Path(state.get("workspace", "/workspace")) / "logs" / "tests" / "[retry_count]")
        test_result_dir = str(
            Path(state.get("workspace", "/workspace")) / "results" / "tests" / "[retry_count]")
        retry_count=state.get("retry_count")

        context = TestRunnerContext(
            workspace=state.get("workspace"),
            mountpoint=state.get("mountpoint"),
            fs_binary=state.get("fs_binary"),
            fs_type=state.get("fs_type"),
            fuse_log_path=state.get("logs").get("fuse"),
            fuse_pid_path=state.get("artifacts").get("fuse_pid"),
            fs_ir=state.get("fs_ir"),
            test_policy=state.get("test_policy"),
            test_template_dir=test_template_dir,
            test_run_dir=test_run_dir,
            test_log_dir=test_log_dir,
            test_result_dir=test_result_dir,
            retry_count=retry_count,
        )

        instructions = (
            f"Test the FUSE filesystem.\n"
            f"This is the {retry_count}-th retry after debugging (0-th means the first try)."
            f"- test template directory: {test_template_dir}\n"
            f"- run tests in directory: {test_run_dir}\n"
            f"- write the test logs in: {test_log_dir}\n"
            f"- write the test report to: {test_result_dir}\n"
        )

        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "Start the filesystem test task using the provided context and policy.",
                },
                {
                    "role": "user",
                    "content": instructions + (f"\n\n{message}" if message else ""),
                },
            ]
        }

        print(f"""
==========================
test runner agent started:
  
payload:
{payload}

context:
{context}
"""
        )

        return self._invoke(payload, context)


def _default_test_policy(fs_ir: dict[str, Any]) -> dict[str, Any]:
    validation = fs_ir.get("validation", {}) if isinstance(fs_ir, dict) else {}
    return {
        "run_preflight": True,
        "run_posix_smoke": validation.get("posix_smoke", True),
        "run_posix_semantics": validation.get("pytest", True),
        "run_stress": False,
        "run_fio": validation.get("fio", False),
        "run_fs_mark": False,
        "run_filebench": validation.get("filebench", False),
        "run_xfstests": validation.get("xfstests", False),
        "timeout_sec": 600,
        "stress": {
            "duration_sec": 15,
            "workers": 4,
        },
        "fio": {
            "runtime_sec": 15,
            "size": "128M",
            "bs": "4k",
            "numjobs": 2,
        },
        "fs_mark": {
            "files": 1000,
            "threads": 4,
            "bytes": 4096,
        },
    }
