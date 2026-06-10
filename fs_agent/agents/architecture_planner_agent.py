from dataclasses import dataclass
from deepagents import create_deep_agent, DeepAgentState
from langchain.agents.structured_output import ToolStrategy, ProviderStrategy
from langchain.chat_models import init_chat_model
import json

from fs_agent.config import Config
from pydantic import BaseModel, Field

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

@dataclass
class ArchitecturePlannerContext:
    fs_ir: dict

class ArchitecturePlannerState(DeepAgentState):
    """State for architecture planner agent."""
    fs_ir: dict

class ModuleSpec(BaseModel):
    name: str = Field(description="Module name")
    responsibility: str = Field(description="Module responsibility")
    files: list[str] = Field(default_factory=list, description="Source files in this module")


class DataStructureSpec(BaseModel):
    name: str = Field(description="Data structure name")
    description: str = Field(description="Purpose and design")
    fields: list[str] = Field(default_factory=list, description="Key fields")

class ArchitecturePlannerResult(BaseModel):
    success: bool = Field(description="Whether architecture design succeeded")

    modules: list[ModuleSpec] = Field(
        default_factory=list,
        description="Module decomposition"
    )

    data_model: dict[str, str] = Field(
        default_factory=dict,
        description="Data model description (name -> description)"
    )

    data_structures: list[DataStructureSpec] = Field(
        default_factory=list,
        description="Key data structures"
    )

    fuse_operations: list[str] = Field(
        default_factory=list,
        description="FUSE operations to implement"
    )

    api_boundaries: list[str] = Field(
        default_factory=list,
        description="Module API boundaries"
    )

    limitations: list[str] = Field(
        default_factory=list,
        description="Known limitations and out-of-scope features"
    )

    threading_model: str = Field(
        default="mutex-based",
        description="Concurrency control strategy"
    )

    memory_management: str = Field(
        default="dynamic allocation with cleanup",
        description="Memory management strategy"
    )

    error_handling: str = Field(
        default="errno-based",
        description="Error handling pattern"
    )

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score of the architecture design"
    )

    reasoning: str = Field(
        default="",
        description="Explanation of architectural decisions"
    )


class ArchitecturePlannerAgent:
    """DeepAgent-based architecture planner that doesn't need a backend."""

    def __init__(self):
        cfg = Config()

        self.model = init_chat_model(
            model=cfg.models.get("architecture_planner", "deepseek:deepseek-v4-flash"),
            extra_body={"thinking": {"type": "disabled"}}
        )

        self.agent = create_deep_agent(
            model=self.model,
            backend=None,
            system_prompt=ARCHITECTURE_PLANNER_AGENT_PROMPT,
            state_schema=ArchitecturePlannerState,
            response_format=ToolStrategy(ArchitecturePlannerResult)
        )

    def _invoke(self, payload, context):
        """Invoke the agent with debug support and retry if structured_response is missing."""
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            if DEBUG:
                print(f"architecture planner agent invoking (attempt {attempt}/{max_retries})")
                from fs_agent.utils.stream_print import print_clean_deepagent_stream
                result = print_clean_deepagent_stream(self.agent, payload, context, True)
            else:
                result = self.agent.invoke(payload, context=context)

            # 检查是否包含 structured_response
            if isinstance(result, dict) and "structured_response" in result:
                print(f"requirement parser agent done: got structured_response on attempt {attempt}")
                return result["structured_response"]

            if isinstance(result, ArchitecturePlannerResult):
                return result

            # 如果没有获取到结构化响应，记录警告并重试
            print(f"[WARNING] Attempt {attempt}: structured_response not found in result (type: {type(result)})")
            if attempt < max_retries:
                print(f"[WARNING] Retrying... ({attempt + 1}/{max_retries})")

        # 所有重试都失败后，抛出异常或返回 None
        raise RuntimeError(
            f"Failed to get structured_response after {max_retries} attempts. "
            f"Last result type: {type(result)}"
        )

    def perform_task(self, state) -> ArchitecturePlannerResult:
        """Design architecture based on FilesystemIR."""

        payload = {
            "messages": [{
                "role": "system",
                "content": "Design architecture based on the FilesystemIR provided."
            }, {
                "role": "user",
                "content": f"Design architecture for this FilesystemIR with structured JSON output:\n{json.dumps(state['fs_ir'], indent=2, ensure_ascii=False)}"
            }]
        }
        context = ArchitecturePlannerContext(
            fs_ir=state["fs_ir"]
        )

        return self._invoke(payload, context=context)