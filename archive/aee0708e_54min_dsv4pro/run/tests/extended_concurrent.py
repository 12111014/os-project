#!/usr/bin/env python3
"""Concurrent read/write tests"""
import os, shutil, sys, multiprocessing as mp
from pathlib import Path

def writer(path, worker_id, count):
    for i in range(count):
        p = Path(path) / f"w{worker_id}_{i}.txt"
        p.write_bytes(f"worker={worker_id} iter={i}".encode())

def reader(path, worker_id, count):
    for i in range(count):
        p = Path(path) / f"w{worker_id}_{i}.txt"
        for _ in range(20):  # poll
            if p.exists():
                content = p.read_bytes()
                if content.startswith(f"worker={worker_id}".encode()):
                    break
            import time; time.sleep(0.01)
        else:
            raise RuntimeError(f"reader {worker_id} didn't find file {i}")

def main() -> int:
    mount = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    root = mount / f".ext-conc-{os.getpid()}"
    root.mkdir()
    try:
        count = 50
        num_workers = 4

        writers = []
        for w in range(num_workers):
            p = mp.Process(target=writer, args=(str(root), w, count))
            writers.append(p)
            p.start()

        for p in writers:
            p.join(10)

        readers = []
        for w in range(num_workers):
            p = mp.Process(target=reader, args=(str(root), w, count))
            readers.append(p)
            p.start()

        for p in readers:
            p.join(30)

        for p in writers + readers:
            if p.exitcode != 0:
                print(f"FAIL: subprocess exited with {p.exitcode}")
                return 1

        # Verify all files exist
        total = 0
        for entry in root.iterdir():
            total += 1
        if total < num_workers * count:
            print(f"FAIL: expected {num_workers * count} files, got {total}")
            return 1

        print("extended_concurrent: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(main())
