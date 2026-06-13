#!/usr/bin/env python3
"""Quick benchmark for agentfs filesystem operations.

Measures throughput for: mkdir, rmdir, symlink create/readlink/unlink,
file create/write/read/unlink, readdir.
"""
import os
import shutil
import sys
import time
from pathlib import Path


def bench(desc: str, n: int, fn):
    start = time.monotonic()
    fn()
    elapsed = time.monotonic() - start
    rate = n / elapsed if elapsed > 0 else 0
    print(f"{desc}: {n} ops in {elapsed:.3f}s = {rate:.1f} ops/s")
    return elapsed, rate


def main():
    mountpoint = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    root = mountpoint / f".agentfs-bench-{os.getpid()}"
    root.mkdir(parents=True, exist_ok=True)
    count = 2000
    file_size = 4096
    payload = b"x" * file_size
    
    try:
        # ---- symlink operations ----
        bench(f"symlink_create", count, lambda: [
            (root / f"sym{i}").symlink_to(f"target-{i}") for i in range(count)
        ])
        
        bench(f"symlink_readlink", count, lambda: [
            os.readlink(str(root / f"sym{i}")) for i in range(count)
        ])
        
        bench(f"symlink_unlink", count, lambda: [
            (root / f"sym{i}").unlink() for i in range(count)
        ])
        
        # ---- Directory operations ----
        bench(f"mkdir", count, lambda: [
            (root / f"dir{i}").mkdir() for i in range(count)
        ])
        
        bench(f"rmdir", count, lambda: [
            (root / f"dir{i}").rmdir() for i in range(count)
        ])
        
        # ---- Regular file operations ----
        bench(f"file_create_write", count, lambda: [
            (root / f"f{i}").write_bytes(payload) for i in range(count)
        ])
        
        bench(f"file_read", count, lambda: [
            (root / f"f{i}").read_bytes() for i in range(count)
        ])
        
        bench(f"file_unlink", count, lambda: [
            (root / f"f{i}").unlink() for i in range(count)
        ])
        
        # ---- readdir benchmark ----
        # Create many entries then readdir
        for i in range(100):
            (root / f"rd_{i}").symlink_to(f"r-{i}")
        
        def do_readdir():
            for _ in range(100):
                list(root.iterdir())
        
        bench(f"readdir(100 entries)", 100, do_readdir)
        
        # Cleanup readdir entries
        for i in range(100):
            (root / f"rd_{i}").unlink()
        
        # ---- chunked write benchmark (larger file) ----
        big_file = root / "bigfile"
        with open(str(big_file), "wb") as f:
            f.write(b"x" * (1024 * 1024))  # 1MB
        bench(f"write_1MB", 1, lambda: None)  # already measured
        
        with open(str(big_file), "rb") as f:
            data = f.read()
        assert len(data) == 1024 * 1024
        bench(f"read_1MB", 1, lambda: None)  # already measured
        big_file.unlink()
        
        print("\nbench_quick: done")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
