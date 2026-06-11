import uuid
from pathlib import Path

from fs_agent.graph import build_graph
from dotenv import load_dotenv

load_dotenv(verbose=True)


def load_user_request(request_file: str | Path = "user_request.md") -> str:
    request_path = Path(request_file)

    if not request_path.exists():
        raise FileNotFoundError(
            f"User request file not found: {request_path}\n"
            f"Please create {request_file} with your filesystem requirements."
        )

    content = request_path.read_text(encoding="utf-8").strip()

    if not content:
        raise ValueError(f"User request file is empty: {request_path}")

    return content

def main():
    graph = build_graph()

    run_id = uuid.uuid4().hex[:8]

    user_request = load_user_request("user_request.md")

    initial_state = {
        "run_id": run_id,
        "user_request": user_request,
        "max_retries": 5,
        "issues": [],
        "patches": [],
    }

    final_state = graph.invoke(initial_state)

    print("Run ID:", run_id)
    print("Final phase:", final_state.get("current_phase"))
    print("Report:", final_state.get("final_report_path"))
    print("Summary:", final_state.get("final_summary"))
    
    print(f"Final state: \n{final_state}")


if __name__ == "__main__":
    main()