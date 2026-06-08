from pathlib import Path
import json


def report_generator_node(state: dict):
    run_id = state["run_id"]
    workspace = Path("runs") / run_id
    report_path = workspace / "report.md"

    report = f"""# Filesystem Agent Report

## Request

{state.get("user_request", "")}

## Status

- Build: {state.get("build_status")}
- Mount: {state.get("mount_status")}
- Test: {state.get("test_status")}
- Retry count: {state.get("retry_count", 0)}

## FS IR

```json
{json.dumps(state.get("fs_ir", {}), indent=2, ensure_ascii=False)}
Issues

{json.dumps(state.get("issues", []), indent=2, ensure_ascii=False)}

Logs

{json.dumps(state.get("logs", {}), indent=2, ensure_ascii=False)}
"""

    report_path.write_text(report, encoding="utf-8")

    return {
        "current_phase": "reported",
        "final_report_path": str(report_path),
        "final_summary": f"Report written to {report_path}",
    }