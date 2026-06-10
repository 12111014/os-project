from deepagents import create_deep_agent, DeepAgentState
from langchain.agents.structured_output import ToolStrategy
from langchain.chat_models import init_chat_model

from fs_agent.config import Config
from fs_agent.schemas.req_agent_outputs import RequirementParserResult

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


class RequirementParserState(DeepAgentState):
    user_request: str


class RequirementParserAgent:

    def __init__(self):
        cfg = Config()

        self.model = init_chat_model(
            model=cfg.models.get("requirement_parser", "deepseek:deepseek-v4-flash"),
            api_key=cfg.api_keys.get("deepseek_key"),
            extra_body={"thinking": {"type": "disabled"}}
        )

        self.agent = create_deep_agent(
            model=self.model,
            backend=None,
            system_prompt=REQUIREMENT_PARSER_AGENT_PROMPT,
            state_schema=RequirementParserState,
            response_format=ToolStrategy(RequirementParserResult),
        )

    def _invoke(self, payload):
        """Invoke the agent with debug support."""
        if DEBUG:
            print("requirement parser agent invoking")
            from fs_agent.utils.stream_print import print_clean_deepagent_stream
            result = print_clean_deepagent_stream(self.agent, payload, True)
        else:
            result = self.agent.invoke(payload)
        return result["structured_response"]

    def perform_task(self, user_request: str) -> RequirementParserResult:
        """Parse user request into structured FilesystemIR."""

        payload = {
            "messages": [{
                "role": "system",
                "content": "Parse the user request into structured FilesystemIR."
            }, {
                "role": "user",
                "content": user_request
            }],
            "user_request": user_request,
        }

        return self._invoke(payload)
