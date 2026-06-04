from typing import TypedDict

from deepagents import create_deep_agent, DeepAgentState
from pathlib import Path

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
        self.model = cfg.models.get("mount_runner")


        self.agent = create_deep_agent(
            model=self.model,
            backend=self.backend,
            system_prompt=MOUNT_RUNNER_AGENT_PROMPT,
            state_schema=MountRunnerState,
        )

    def _invoke(self, payload):
        last = None
        # stream output for debug
        if DEBUG:
            # from fs_agent.utils.stream_print import print_clean_deepagent_stream
            # result = print_clean_deepagent_stream(self.agent, payload, False)
            # return result

            for mode, chunk in self.agent.stream(
                    payload,
                    stream_mode=["messages"],
            ):
                print(f"\n=== DEEPAGENT {mode} ===")
                print(chunk)
                last = chunk
            return last
        return self.agent.invoke(payload)

    def perform_task(self, state):
        payload = {
            "messages": [{"role": "system", "content": "Start to perform the mount task using the state provided."}],
            "workspace": state["workspace"],
            "source_dir": state["source_root"],
            "mountpoint": state["mountpoint"],
            "log_path": str(Path(state["workspace"]) / "logs" / "fuse.log"),
            "pid_path": str(Path(state["workspace"]) / "run" / "fuse.pid"),
        }
        return self._invoke(payload)

