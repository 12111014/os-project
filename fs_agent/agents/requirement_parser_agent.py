from dataclasses import dataclass
from deepagents import create_deep_agent
from langchain.agents.structured_output import ToolStrategy

from fs_agent.config import Config
from typing import Literal
from pydantic import BaseModel, Field
from fs_agent.utils.system_prompt import build_system_prompt


REQUIREMENT_PARSER_AGENT_PROMPT = """
You are a Filesystem Requirements Engineer specializing in FUSE filesystems.

Your job:
- Analyze the user's natural language request carefully.
- Extract key requirements: storage type, features, operations, validation needs.
- Map requirements to structured FilesystemIR fields.
- Make reasonable inferences for unstated requirements based on context.
- Detect ambiguities or conflicts and report them as warnings.
- Provide confidence score and reasoning for your decisions.

Decision rules:
1. Storage type selection:
   - "简单"、"临时"、"缓存"、"测试" → storage.type = "memory"
   - "持久化"、"永久"、"断电不丢失" → storage.type = "image_file"
   - "穿透"、"overlay"、"映射到真实目录" → storage.type = "passthrough"

2. Feature selection:
   - "符号链接"、"symlink" → features.symlink = True
   - "硬链接"、"hardlink" → features.hardlink = True
   - "扩展属性"、"xattr" → features.xattrs = True
   - "日志"、"journal"、"崩溃一致性" → features.journaling = True
   - "权限控制" → features.permissions = "basic" or "full"

3. Operation selection:
   - Always include: getattr, readdir, open, read, write
   - If mentions "创建文件": add create, unlink
   - If mentions "目录": add mkdir, rmdir
   - If mentions "重命名" or "移动": add rename
   - If mentions "截断": add truncate
   - If mentions "权限": add chmod
   - If mentions "同步": add fsync

4. Validation selection:
   - Simple/test filesystem → only posix_smoke = True
   - Production-ready → enable pytest, fio
   - High-performance → enable fio, filebench
   - Linux compatibility → enable xfstests

Process:
1. Read the user_request from the state.
2. Think step by step about what each part of the request means.
3. Consider edge cases and ambiguities.
4. Generate the complete RequirementParserResult JSON.

Output ONLY valid JSON matching the RequirementParserResult schema.
Do not include any prose outside the JSON structure.
"""

DEBUG = Config().debug


@dataclass
class RequirementParserContext:
    user_request: str


class StorageSpec(BaseModel):
    type: str = Field(
        default="memory",
        description="Storage backend type: memory, image_file, or passthrough"
    )
    block_size: int = Field(default=4096, description="Block size in bytes")
    image_size_mb: int = Field(
        default=1024, description="Image size in MB for image_file storage")


class FeatureSpec(BaseModel):
    directories: bool = Field(default=True, description="Support directories")
    symlink: bool = Field(default=False, description="Support symbolic links")
    hardlink: bool = Field(default=False, description="Support hard links")
    permissions: Literal["none", "basic"] = Field(
        default="basic", description="Permission model")
    journaling: bool = Field(default=False, description="Enable journaling")
    xattrs: bool = Field(
        default=False, description="Support extended attributes")


class ValidationSpec(BaseModel):
    posix_smoke: bool = Field(
        default=True, description="Run POSIX smoke tests")
    pytest: bool = Field(default=True, description="Run pytest suite")
    fio: bool = Field(default=False, description="Run fio benchmarks")
    filebench: bool = Field(
        default=False, description="Run filebench benchmarks")
    xfstests: bool = Field(default=False, description="Run xfstests suite")


class RequirementParserResult(BaseModel):
    success: bool = Field(description="Whether parsing succeeded")

    name: str = Field(
        default="agentfs",
        description="Filesystem name"
    )

    target: Literal["fuse"] = Field(
        default="fuse",
        description="Target framework"
    )

    language: Literal["c", "rust", "python"] = Field(
        default="c",
        description="Implementation language"
    )

    backend: Literal["libfuse3"] = Field(
        default="libfuse3",
        description="Backend library"
    )

    storage: StorageSpec = Field(
        default_factory=StorageSpec,
        description="Storage backend specification"
    )

    features: FeatureSpec = Field(
        default_factory=FeatureSpec,
        description="Feature flags"
    )

    operations: list[str] = Field(
        default_factory=list,
        description="List of FUSE operations to implement"
    )

    validation: ValidationSpec = Field(
        default_factory=ValidationSpec,
        description="Validation and testing configuration"
    )

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score of the parsing result"
    )

    reasoning: str = Field(
        default="",
        description="Explanation of design decisions"
    )


class RequirementParserAgent:

    def __init__(self):
        cfg = Config()

        self.model = cfg.build_model("requirement_parser")

        self.agent = create_deep_agent(
            model=self.model,
            backend=None,
            system_prompt=build_system_prompt(REQUIREMENT_PARSER_AGENT_PROMPT),
            context_schema=RequirementParserContext,
            response_format=ToolStrategy(RequirementParserResult),
        )

    def _invoke(self, payload, context):
        """Invoke the agent with debug support."""
        if DEBUG:
            print("requirement parser agent invoking")
            from fs_agent.utils.stream_print import print_clean_deepagent_stream
            result = print_clean_deepagent_stream(
                self.agent, payload, context, True)
        else:
            result = self.agent.invoke(payload, context=context)
        return result["structured_response"]

    def perform_task(self, state) -> RequirementParserResult:
        """Parse user request into structured FilesystemIR."""

        payload = {
            "messages": [{
                "role": "system",
                "content": "Parse the user request into structured FilesystemIR."
            }, {
                "role": "user",
                "content": state["user_request"]
            }]
        }
        context = RequirementParserContext(
            user_request=state["user_request"]
        )

        return self._invoke(payload, context)
