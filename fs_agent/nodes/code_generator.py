"""Code generator node.

Thin wrapper around :class:`CodeGeneratorAgent`. The deepagents-based agent
generates the filesystem source (grounded on the libfuse examples and a
known-good skeleton) and writes the files directly into the sandbox source
directory. This node only translates the agent's structured result into the
graph state.
"""

from fs_agent.utils.sandbox_manager import sandbox_from_state
from fs_agent.agents.code_generator_agent import CodeGeneratorAgent, CodeGeneratorResult


def code_generator_node(state: dict):
    agent = CodeGeneratorAgent(sandbox_from_state(state))
    result: CodeGeneratorResult = agent.perform_task(state)

    print(f"""
================================
code generator agent result: 
{result}
"""
          )

    if result.status == "failed":
        return {
            "current_phase": "code_generation_failed",
            "issues": [issue.model_dump() for issue in result.issues],
        }

    return {
        "current_phase": "code_generated",
        "source_root": result.source_root,
        "build_dir": state["build_dir"],
        "fs_binary": state["fs_binary"],
        "artifacts": {
            "generated_files": result.files,
        },
        # "patches": [
        #     {
        #         "id": f"codegen-{result.method}",
        #         "summary": result.summary,
        #         "files_changed": result.files,
        #     }
        # ],
    }
