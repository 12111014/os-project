from fs_agent.agents.debugger_agent import DebuggerAgent, DebuggerResult
from fs_agent.utils.sandbox_manager import sandbox_from_state


def debugger_node(state: dict):
    retry_count = state.get("retry_count", 0)
    
    agent = DebuggerAgent(sandbox_from_state(state))
    result: DebuggerResult = agent.perform_task(state)
    
    print(f"""
================================
test runner agent result: 
{result}
"""
)

    return {
        "current_phase": "debugged",
        "debug_status": result.debug_status,
        "retry_count": retry_count + 1,
        "debug_history": [{"root_cause": result.root_cause, "diagnosis": result.diagnosis}],
        "issues": [issue.model_dump() for issue in result.issues],
        "patches": [patch.model_dump() for patch in result.patches],
        "debug_next_phase": result.next_phase
    }