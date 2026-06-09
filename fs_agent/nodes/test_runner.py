from fs_agent.utils.sandbox_manager import sandbox_from_state
from fs_agent.agents.test_runner_agent import TestRunnerAgent, TestAgentResult


def test_runner_node(state: dict):
    agent = TestRunnerAgent(sandbox_from_state(state))
    result: TestAgentResult = agent.perform_task(state)

    print(f"""
================================
test runner agent result: 
{result}
"""
)

    if result.test_status == "passed":
        return {
            "current_phase": "test_passed",
            "test_status": "passed",
            "logs": {"test": result.logs},
            "artifacts": {"test": result.artifacts}
        }
    elif result.test_status == "degraded":
        return {
            "current_phase": "test_degraded",
            "test_status": "degraded",
            "logs": {"test": result.logs},
            "artifacts": {"test": result.artifacts},
            "issues": [issue.model_dump() for issue in result.issues],
        }
    else:
        return {
            "current_phase": "test_failed",
            "test_status": "failed",
            "logs": {"test": result.logs},
            "artifacts": {"test": result.artifacts},
            "issues": [issue.model_dump() for issue in result.issues],
        }
