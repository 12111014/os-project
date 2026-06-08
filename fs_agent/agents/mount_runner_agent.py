from deepagents import create_deep_agent, DeepAgentState
from langchain.agents.structured_output import ToolStrategy
from langchain.chat_models import init_chat_model
from pathlib import Path

from fs_agent.config import Config
from fs_agent.utils.sandbox_backend import SandboxBackend
from fs_agent.utils.sandbox_manager import sandbox_from_state, SandboxRef
from fs_agent.schemas.agent_outputs import MountAgentResult

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
    """

DEBUG = Config().debug


class MountRunnerState(DeepAgentState):
    workspace: str
    source_dir: str
    mountpoint: str
    log_path: str
    pid_path: str


class MountRunnerAgent:
    def __init__(self, sandbox: SandboxRef):
        cfg = Config()
        self.backend = SandboxBackend(sandbox)
        self.model = init_chat_model(
            model=cfg.models.get("mount_runner"),
            extra_body={"thinking": {"type": "disabled"}}
        )

        self.agent = create_deep_agent(
            model=self.model,
            backend=self.backend,
            system_prompt=MOUNT_RUNNER_AGENT_PROMPT,
            state_schema=MountRunnerState,
            # response_format=MountAgentResult,
            response_format=ToolStrategy(MountAgentResult),
        )

    def _invoke(self, payload):
        if DEBUG:
            print("mount runner agent invoking")
            from fs_agent.utils.stream_print import print_clean_deepagent_stream
            result = print_clean_deepagent_stream(self.agent, payload, True)
        else:
            result = self.agent.invoke(payload)
        return result["structured_response"]

    def perform_task(self, state, message=""):
        payload = {
            "messages": [{
                "role": "system",
                "content": "Start to perform the mount task using the state provided."
            }, {
                "role": "user",
                "content": message
            }],
            "workspace": state["workspace"],
            "source_dir": state["source_root"],
            "mountpoint": state["mountpoint"],
            "log_path": str(Path(state["workspace"]) / "logs" / "fuse.log"),
            "pid_path": str(Path(state["workspace"]) / "run" / "fuse.pid"),
        }
        return self._invoke(payload)
