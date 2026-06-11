from pathlib import Path

from fs_agent.agents.requirement_parser_agent import RequirementParserAgent
from fs_agent.config import Config
from fs_agent.schemas.fs_ir import FilesystemIR

DEBUG = Config().debug


def requirement_parser_node(state: dict):
    run_id = state["run_id"]
    workspace = Path("runs") / run_id
    workspace.mkdir(parents=True, exist_ok=True)

    user_request = state.get("user_request", "")

    if not user_request:
        raise ValueError(
            "user_request is empty in state. Did main.py load it correctly?")

    print(f"\n[requirement_parser] Parsing user request ({len(user_request)} chars)...")
    agent = RequirementParserAgent()
    result = agent.perform_task(state)

    # 将 Agent 输出转换为 FilesystemIR
    fs_ir = FilesystemIR(
        name=result.name,
        target=result.target,
        language=result.language,
        backend=result.backend,
        storage=result.storage.model_dump(),
        features=result.features.model_dump(),
        operations=result.operations,
        validation=result.validation.model_dump(),
    )

    # 保存置信度和推理过程供调试
    print(f"[requirement_parser] Confidence: {result.confidence:.2f}")
    print(f"[requirement_parser] Reasoning: {result.reasoning[:200]}...")

    (workspace / "requirement_reasoning.txt").write_text(
        f"Confidence: {result.confidence}\n\nReasoning:\n{result.reasoning}",
        encoding="utf-8"
    )

    # 保存原始 Agent 输出
    (workspace / "requirement_result.json").write_text(
        result.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    if DEBUG:
        print(f"[requirement_parser] ✓ Parsed successfully")
        print(f"[requirement_parser]   Storage: {fs_ir.storage}")
        print(
            f"[requirement_parser]   Operations: {len(fs_ir.operations)}")

    fs_ir_path = workspace / "fs_ir.json"
    fs_ir_path.write_text(
        fs_ir.model_dump_json(indent=2),
        encoding="utf-8",
    )

    return {
        "current_phase": "requirement_parsed",
        "fs_ir": fs_ir.model_dump(),
        "fs_ir_path": str(fs_ir_path),
    }
