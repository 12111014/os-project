#!/usr/bin/env python3
from __future__ import annotations

import multiprocessing as mp
import os
import shutil
import sys
import time
from pathlib import Path


def worker(root: str, worker_id: int, deadline: float) -> None:
    base = Path(root) / f"w{worker_id}"
    base.mkdir(parents=True, exist_ok=True)
    i = 0
    while time.monotonic() < deadline:
        directory = base / f"d{i % 32}"
        directory.mkdir(exist_ok=True)
        path = directory / f"f{i}.txt"
        path.write_bytes(f"worker={worker_id} iter={i}\n".encode())
        assert path.read_bytes().startswith(f"worker={worker_id}".encode())
        renamed = directory / f"g{i}.txt"
        path.rename(renamed)
        renamed.unlink()
        try:
            directory.rmdir()
        except OSError:
            pass
        i += 1


def main() -> int:
    mountpoint = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    duration = int(os.environ.get("STRESS_DURATION_SEC", "15"))
    workers = int(os.environ.get("STRESS_WORKERS", "4"))
    root = mountpoint / f".agentfs-stress-{os.getpid()}"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    deadline = time.monotonic() + duration
    processes = [mp.Process(target=worker, args=(str(root), n, deadline)) for n in range(workers)]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(duration + 10)
        failed = [process.exitcode for process in processes if process.exitcode != 0]
        if failed:
            raise RuntimeError(f"stress workers failed: {failed}")
        print(f"stress_metadata: passed workers={workers} duration_sec={duration}")
        return 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(5)
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
