def debugger_node(state: dict):
    retry_count = state.get("retry_count", 0)

    return {
        "current_phase": "debugged",
        "retry_count": retry_count + 1,
        "issues": [
            {
                "type": "debug_note",
                "summary": "MVP debug agent does not patch yet. Inspect logs manually.",
            }
        ],
    }