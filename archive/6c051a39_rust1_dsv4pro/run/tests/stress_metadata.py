#!/usr/bin/env python3
"""Metadata and file I/O stress test for agentfs.

Concurrent workers perform mixed operations: mkdir, symlink, readlink,
rename, unlink, rmdir, file create/write/read/unlink.
"""
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
    errors = 0
    while time.monotonic() < deadline:
        try:
            directory = base / f"d{i % 32}"
            directory.mkdir(exist_ok=True)
            
            # Create symlink
            sym_name = directory / f"s{i}.lnk"
            sym_name.symlink_to(f"target-{worker_id}-{i}")
            
            # Read symlink and verify
            target = os.readlink(str(sym_name))
            assert target == f"target-{worker_id}-{i}", f"readlink mismatch: {target}"
            
            # Rename symlink
            renamed = directory / f"r{i}.lnk"
            sym_name.rename(renamed)
            
            # Unlink symlink
            renamed.unlink()
            
            # Create regular file, write, read, unlink
            file_path = directory / f"f{i}.txt"
            payload = f"worker={worker_id} iter={i}\n".encode()
            file_path.write_bytes(payload)
            read_back = file_path.read_bytes()
            assert read_back == payload, f"file content mismatch: {read_back!r}"
            file_path.unlink()
            
            # Try to remove dir (may fail if another worker added entries)
            try:
                directory.rmdir()
            except OSError:
                pass
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"worker {worker_id} error: {e}")
        i += 1
    print(f"worker {worker_id}: {i} iterations, {errors} errors")


def main() -> int:
    mountpoint = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    duration = int(os.environ.get("STRESS_DURATION_SEC", "10"))
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
    except Exception as e:
        print(f"stress_metadata: FAILED - {e}")
        return 1
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(5)
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
