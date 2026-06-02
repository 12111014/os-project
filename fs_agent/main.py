import uuid
from fs_agent.graph import build_graph


def main():
    graph = build_graph()

    run_id = uuid.uuid4().hex[:8]

    initial_state = {
        "run_id": run_id,
        "user_request": (
            "生成一个基于 FUSE/libfuse3 的简单内存文件系统，"
            "支持 create/read/write/readdir/mkdir/unlink/rename/truncate。"
        ),
        "max_retries": 2,
        "issues": [],
        "patches": [],
    }

    final_state = graph.invoke(initial_state)

    print("Run ID:", run_id)
    print("Final phase:", final_state.get("current_phase"))
    print("Report:", final_state.get("final_report_path"))
    print("Summary:", final_state.get("final_summary"))


if __name__ == "__main__":
    main()