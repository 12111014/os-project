"""Build runner node.

Thin wrapper around :class:`BuildRunnerAgent`. The deepagents-based agent
compiles the generated filesystem inside the sandbox, normalises the produced
binary to ``build/agentfs`` and captures the build log. This node only
translates the agent's structured result into the graph state.
"""

from fs_agent.utils.sandbox_manager import sandbox_from_state
from fs_agent.agents.build_runner_agent import BuildRunnerAgent, BuildRunnerResult


def build_runner_node(state: dict):
    agent = BuildRunnerAgent(sandbox_from_state(state))
    result: BuildRunnerResult = agent.perform_task(state)

    print(f"""
================================
build runner agent result: 
{result}
"""
          )

    if result.build_status == "passed":
        return {
            "current_phase": "build_passed",
            "build_status": "passed",
            "logs": {"build": result.log_path},
            "artifacts": {"fs_binary": result.binary_path}
        }

    return {
        "current_phase": "build_failed",
        "build_status": "failed",
        "logs": {"build": result.log_path},
        "issues": [issue.model_dump() for issue in result.issues],
    }
