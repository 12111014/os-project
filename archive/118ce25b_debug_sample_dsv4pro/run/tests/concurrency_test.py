#!/usr/bin/env python3
"""Concurrency correctness test: parallel creates, writes, reads, unlinks."""
from __future__ import annotations

import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def worker(mountpoint: str, worker_id: int, iterations: int) -> int:
    base = Path(mountpoint) / f".concurrency-w{worker_id}-{os.getpid()}"
    base.mkdir(parents=True, exist_ok=True)
    errors = 0
    for i in range(iterations):
        fpath = base / f"file_{i}"
        data = f"w{worker_id}-i{i}-{"x"*100}".encode()[:128]
        try:
            fpath.write_bytes(data)
            readback = fpath.read_bytes()
            if readback != data:
                errors += 1
            fpath.unlink()
        except Exception:
            errors += 1
    try:
        base.rmdir()
    except OSError:
        pass
    return errors


def main() -> int:
    mountpoint = os.environ.get("MOUNTPOINT", "/mnt/agentfs")
    workers = 8
    iterations = 100
    root = Path(mountpoint) / f".concurrency-root-{os.getpid()}"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()

    try:
        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(worker, str(root), w, iterations) for w in range(workers)]
            total_errors = sum(f.result() for f in as_completed(futures))
        elapsed = time.monotonic() - start

        if total_errors > 0:
            print(f"concurrency_test: FAILED errors={total_errors}")
            return 1
        print(f"concurrency_test: passed workers={workers} iter_per_worker={iterations} elapsed={elapsed:.2f}s")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
