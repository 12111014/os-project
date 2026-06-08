from langgraph.graph import StateGraph, START, END

from fs_agent.state import FSAgentState

from fs_agent.nodes.create_sandbox import create_sandbox_node
from fs_agent.nodes.requirement_parser import requirement_parser_node
from fs_agent.nodes.architecture_planner import architecture_planner_node
from fs_agent.nodes.code_generator import code_generator_node
from fs_agent.nodes.build_runner import build_runner_node
from fs_agent.nodes.mount_runner import mount_runner_node
from fs_agent.nodes.test_runner import test_runner_node
from fs_agent.nodes.debugger import debugger_node
from fs_agent.nodes.report_generator import report_generator_node
from fs_agent.nodes.cleanup import cleanup_node


def route_after_build(state: FSAgentState) -> str:
    if state.get("build_status") == "passed":
        return "mount_runner"
    return "debugger"


def route_after_mount(state: FSAgentState) -> str:
    if state.get("mount_status") == "mounted":
        return "test_runner"
    return "debugger"


def route_after_test(state: FSAgentState) -> str:
    if state.get("test_status") == "passed":
        return "cleanup"
    return "debugger"


def route_after_debug(state: FSAgentState) -> str:
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)

    if retry_count >= max_retries:
        return "cleanup"

    # MVP 阶段：debug 不修代码，可以直接 cleanup
    # 后续接入 patch 后，改成回到 build_runner
    return "cleanup"



def build_graph():
    graph = StateGraph(FSAgentState)

    graph.add_node("create_sandbox", create_sandbox_node)
    graph.add_node("requirement_parser", requirement_parser_node)
    graph.add_node("architecture_planner", architecture_planner_node)
    graph.add_node("code_generator", code_generator_node)
    graph.add_node("build_runner", build_runner_node)
    graph.add_node("mount_runner", mount_runner_node)
    graph.add_node("test_runner", test_runner_node)
    graph.add_node("debugger", debugger_node)
    graph.add_node("cleanup", cleanup_node)
    graph.add_node("report_generator", report_generator_node)

    graph.add_edge(START, "create_sandbox")
    graph.add_edge("create_sandbox", "requirement_parser")
    graph.add_edge("requirement_parser", "architecture_planner")
    graph.add_edge("architecture_planner", "code_generator")
    graph.add_edge("code_generator", "build_runner")

    graph.add_conditional_edges(
        "build_runner",
        route_after_build,
        {
            "mount_runner": "mount_runner",
            "debugger": "debugger",
        },
    )

    graph.add_conditional_edges(
        "mount_runner",
        route_after_mount,
        {
            "test_runner": "test_runner",
            "debugger": "debugger",
        },
    )

    graph.add_conditional_edges(
        "test_runner",
        route_after_test,
        {
            "cleanup": "cleanup",
            "debugger": "debugger",
        },
    )

    graph.add_conditional_edges(
        "debugger",
        route_after_debug,
        {
            "build_runner": "build_runner",
            "cleanup": "cleanup",
        },
    )

    graph.add_edge("cleanup", "report_generator")
    graph.add_edge("report_generator", END)
    
    compiled_graph = graph.compile()
    
    print(compiled_graph.get_graph(xray=True).draw_mermaid())
    
    return compiled_graph