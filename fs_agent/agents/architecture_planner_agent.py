from deepagents import create_deep_agent, DeepAgentState
from langchain.agents.structured_output import ToolStrategy
from langchain.chat_models import init_chat_model
import json

from fs_agent.config import Config
from fs_agent.schemas.arch_agent_outputs import ArchitecturePlanResult

ARCHITECTURE_PLANNER_AGENT_PROMPT = """
You are a Filesystem Architect specializing in FUSE-based filesystem design.

Your job:
- Analyze the FilesystemIR specification thoroughly.
- Design a modular software architecture appropriate for the storage type.
- Define clear module boundaries and responsibilities.
- Specify key data structures and their relationships.
- Identify API boundaries between modules.
- State explicit limitations and out-of-scope features.
- Provide confidence score and reasoning for architectural decisions.

Architecture patterns by storage type:

1. Memory filesystem (storage.type = "memory"):
   - Modules: main, fuse_ops, inode_table, dir_ops, storage_backend, path_utils
   - Data model: hash map from path to inode, bytearray per file
   - Threading: single global mutex protecting inode table
   - Memory: dynamic allocation, grow as needed

2. Passthrough filesystem (storage.type = "passthrough"):
   - Modules: main, fuse_ops, path_mapper, syscall_wrapper, permission_checker
   - Data model: map from virtual path to real path
   - Threading: per-operation locking, delegate to underlying FS
   - Memory: minimal, mostly pass-through to real FS

3. Image file filesystem (storage.type = "image_file"):
   - Modules: main, fuse_ops, block_manager, superblock, btree, journal, cache
   - Data model: disk blocks, inode table on disk, free space bitmap
   - Threading: fine-grained locks per block/inode
   - Memory: buffer cache for hot blocks

For each IR, you must specify:
- modules: List of modules with clear responsibilities
- data_model: Description of core data structures
- data_structures: Key structs/classes with field descriptions
- fuse_operations: Copy from IR's operations list
- api_boundaries: How modules interact (function calls, data sharing)
- limitations: What is explicitly NOT implemented
- threading_model: Concurrency control strategy
- memory_management: Allocation and cleanup strategy
- error_handling: Error propagation pattern

Process:
1. Read the fs_ir from the state.
2. Analyze storage type and feature requirements.
3. Choose appropriate architecture pattern.
4. Design modules and data structures.
5. Generate the complete ArchitecturePlanResult JSON.

Output ONLY valid JSON matching the ArchitecturePlanResult schema.
Do not include any prose outside the JSON structure.
"""

DEBUG = Config().debug


class ArchitecturePlannerState(DeepAgentState):
    """State for architecture planner agent."""
    fs_ir: dict


class ArchitecturePlannerAgent:
    """DeepAgent-based architecture planner that doesn't need a backend."""

    def __init__(self):
        cfg = Config()

        self.model = init_chat_model(
            model=cfg.models.get("architecture_planner", "deepseek:deepseek-v4-flash"),
            api_key=cfg.api_keys.get("deepseek_key"),
            extra_body={"thinking": {"type": "disabled"}}
        )

        self.agent = create_deep_agent(
            model=self.model,
            backend=None,
            system_prompt=ARCHITECTURE_PLANNER_AGENT_PROMPT,
            state_schema=ArchitecturePlannerState,
            response_format=ToolStrategy(ArchitecturePlanResult),
        )

    def _invoke(self, payload):
        """Invoke the agent with debug support."""
        if DEBUG:
            print("architecture planner agent invoking")
            from fs_agent.utils.stream_print import print_clean_deepagent_stream
            result = print_clean_deepagent_stream(self.agent, payload, True)
        else:
            result = self.agent.invoke(payload)
        return result["structured_response"]

    def perform_task(self, fs_ir: dict) -> ArchitecturePlanResult:
        """Design architecture based on FilesystemIR."""

        payload = {
            "messages": [{
                "role": "system",
                "content": "Design architecture based on the FilesystemIR provided."
            }, {
                "role": "user",
                "content": f"Design architecture for this FilesystemIR:\n{json.dumps(fs_ir, indent=2, ensure_ascii=False)}"
            }],
            "fs_ir": fs_ir,
        }

        return self._invoke(payload)

