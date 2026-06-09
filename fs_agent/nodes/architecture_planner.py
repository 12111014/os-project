import json
from pathlib import Path

from fs_agent.agents.architecture_planner_agent import ArchitecturePlannerAgent


def architecture_planner_node(state: dict):
    run_id = state["run_id"]
    workspace = Path("runs") / run_id

    fs_ir = state.get("fs_ir", {})
    if not fs_ir:
        raise ValueError("fs_ir is empty in state. Did requirement_parser_node run correctly?")

    try:
        print(f"\n[architecture_planner] Designing architecture for {fs_ir.get('name', 'unknown')}...")
        print(f"[architecture_planner]   Storage type: {fs_ir.get('storage', {}).get('type', 'unknown')}")
        print(f"[architecture_planner]   Operations: {len(fs_ir.get('operations', []))}")

        agent = ArchitecturePlannerAgent()
        result = agent.perform_task(fs_ir)

        print(f"[architecture_planner] ✓ Agent completed successfully result:{result}")

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
        }

        issues = []
        if result.warnings:
            # issues.extend([
            #     {"type": "architecture_warning", "summary": w}
            #     for w in result.warnings
            # ])
            print(f"[architecture_planner] Warnings: {len(result.warnings)}")
            for w in result.warnings:
                print(f"  ⚠ {w}")

        print(f"[architecture_planner] Confidence: {result.confidence:.2f}")
        print(f"[architecture_planner] Reasoning: {result.reasoning[:200]}...")

        (workspace / "architecture_reasoning.txt").write_text(
            f"Confidence: {result.confidence}\n\nReasoning:\n{result.reasoning}",
            encoding="utf-8"
        )

        # 保存原始 Agent 输出
        (workspace / "architecture_result.json").write_text(
            result.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # 打印架构摘要
        print(f"[architecture_planner] ✓ Designed successfully")
        print(f"[architecture_planner]   Modules: {len(result.modules)}")
        for module in result.modules:
            print(f"[architecture_planner]     - {module.name}: {module.responsibility[:50]}...")
        print(f"[architecture_planner]   Data structures: {len(result.data_structures)}")
        print(f"[architecture_planner]   Limitations: {len(result.limitations)}")
        print(f"[architecture_planner]   Threading: {result.threading_model}")
        print(f"[architecture_planner]   Memory: {result.memory_management}\n")

    except Exception as exc:
        print(f"[architecture_planner] ✗ Agent failed: {exc}")
        print(f"[architecture_planner] Using template architecture...\n")

        plan = {
            "modules": [
                "main",
                "fuse_ops",
                "inode",
                "dir",
                "storage",
                "path",
                "tests",
            ],
            "data_model": {
                "inode": "in-memory inode table for MVP",
                "directory": "hash map from name to inode id",
                "file_data": "bytearray per file",
            },
            "fuse_operations": state["fs_ir"]["operations"],
            "limitations": [
                "no crash consistency",
                "no hardlink",
                "no xattr",
                "no journal",
            ],
        }

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