from __future__ import annotations

from typing import TypedDict, Literal, Optional, Any
from typing_extensions import Annotated
import operator


class FSAgentState(TypedDict, total=False):
    # 基本信息
    run_id: str
    user_request: str
    current_phase: str

    # sandbox 信息
    sandbox: dict[str, Any]
    workspace: str
    source_root: str
    build_dir: str
    fs_binary: str
    mountpoint: str
    template_dir: str
    fs_type: str

    # 规格与架构
    fs_ir: dict[str, Any]
    fs_ir_path: str
    architecture_plan: dict[str, Any]
    architecture_path: str

    # 构建/挂载/测试状态
    build_status: Literal["not_started", "passed", "failed"]
    mount_status: Literal["not_started", "mounted", "failed", "cleaned"]
    test_status: Literal["not_started", "passed", "failed", "degraded"]

    # 日志与产物
    logs: Annotated[dict[str, str], operator.or_]
    artifacts: Annotated[dict[str, str], operator.or_]

    # 问题和修复记录，用 reducer 追加
    issues: Annotated[list[dict[str, Any]], operator.add]
    patches: Annotated[list[dict[str, Any]], operator.add]

    # 控制循环
    retry_count: int
    max_retries: int

    # 最终报告
    final_report_path: str
    final_summary: str