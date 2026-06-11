from fs_agent.agents.report_generator_agent import ReportGeneratorAgent, ReportGeneratorResult
from fs_agent.utils.sandbox_manager import sandbox_from_state

def report_generator_node(state: dict):
    agent = ReportGeneratorAgent(sandbox_from_state(state))
    result: ReportGeneratorResult = agent.perform_task(state)

    return {
        "current_phase": "reported",
        "final_report_path": result.final_report_path,
        "final_summary": result.final_summary,
    }