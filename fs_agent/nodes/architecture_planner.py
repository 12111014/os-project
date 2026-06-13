import json
from pathlib import Path

from fs_agent.agents.architecture_planner_agent import ArchitecturePlannerAgent
from fs_agent.config import Config

DEBUG = Config().debug


def architecture_planner_node(state: dict):
    run_id = state["run_id"]
    workspace = Path("runs") / run_id

    fs_ir = state.get("fs_ir", {})
    if not fs_ir:
        raise ValueError(
            "fs_ir is empty in state. Did requirement_parser_node run correctly?")

    print(
        f"\n[architecture_planner] Designing architecture for {fs_ir.get('name', 'unknown')}...")
    print(
        f"[architecture_planner]   Storage type: {fs_ir.get('storage', {}).get('type', 'unknown')}")
    print(
        f"[architecture_planner]   Operations: {len(fs_ir.get('operations', []))}")

    agent = ArchitecturePlannerAgent()
    result = agent.perform_task(state)

    print(
        f"[architecture_planner] ✓ Agent completed successfully result:{result}")

    plan = {
        "modules": [m.model_dump() for m in result.modules],
        "data_model": result.data_model,
        "data_structures": [ds.model_dump() for ds in result.data_structures],
        "fuse_operations": result.fuse_operations,
        "api_boundaries": result.api_boundaries,
        "limitations": result.limitations,
        "threading_model": result.threading_model,
        "memory_management": result.memory_management,
        "error_handling": result.error_handling,
        "dependencies":result.dependencies,
    }
    
    plan = result.model_dump()

    # 保存原始 Agent 输出
    (workspace / "architecture_result.json").write_text(
        result.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # 打印架构摘要
    if DEBUG:
        print(f"[architecture_planner] ✓ Designed successfully")
        print(f"[architecture_planner]   Modules: {len(result.modules)}")
        for module in result.modules:
            print(
                f"[architecture_planner]     - {module.name}: {module.responsibility[:50]}...")
            print(
                f"[architecture_planner]   Data structures: {len(result.data_structures)}")
            print(
                f"[architecture_planner]   Limitations: {len(result.limitations)}")
            print(
                f"[architecture_planner]   Threading: {result.threading_model}")
            print(
                f"[architecture_planner]   Memory: {result.memory_management}\n")

    architecture_path = workspace / "architecture.json"
    architecture_path.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "current_phase": "architecture_planned",
        "architecture_plan": plan,
        "architecture_path": str(architecture_path),
    }
