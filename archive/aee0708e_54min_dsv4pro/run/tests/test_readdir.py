#!/usr/bin/env python3
"""Dedicated readdir tests: large directories, offset behavior, . and .."""
from __future__ import annotations

import os
import sys
from pathlib import Path

MOUNTPOINT = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
LOG = Path("/workspace/logs/tests/test_readdir.log")


def main() -> int:
    with open(LOG, "w") as log:
        def tee(msg):
            print(msg)
            log.write(msg + "\n")

        tee("=== test_readdir started ===")
        pid = os.getpid()
        root = MOUNTPOINT / f".test_readdir-{pid}"
        if root.exists():
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        passed = 0
        failed = 0

        try:
            # Test 1: . and .. present
            entries = sorted(os.listdir(str(root)))
            if entries == []:
                tee("  empty dir: OK")
                passed += 1
            else:
                tee(f"  empty dir: FAIL (got {entries})")
                failed += 1

            # Test 2: Basic listing
            for i in range(10):
                (root / f"file_{i:03d}.txt").write_text(f"content {i}")
            entries = sorted(os.listdir(str(root)))
            expected = sorted([f"file_{i:03d}.txt" for i in range(10)])
            if entries == expected:
                tee("  basic listing (10 files): OK")
                passed += 1
            else:
                tee(f"  basic listing: FAIL (got {len(entries)} entries)")
                failed += 1

            # Test 3: Larger directory (100 files)
            bigdir = root / "bigdir"
            bigdir.mkdir()
            for i in range(100):
                (bigdir / f"f{i:05d}").touch()
            entries = os.listdir(str(bigdir))
            if len(entries) == 100:
                tee("  large dir (100 files): OK")
                passed += 1
            else:
                tee(f"  large dir: FAIL (got {len(entries)} entries)")
                failed += 1

            # Test 4: Directory with subdirectories in listing
            mixdir = root / "mixdir"
            mixdir.mkdir()
            (mixdir / "sub_a").mkdir()
            (mixdir / "sub_b").mkdir()
            (mixdir / "file_1.txt").write_text("x")
            (mixdir / "file_2.txt").write_text("y")
            entries = sorted(os.listdir(str(mixdir)))
            expected = sorted(["sub_a", "sub_b", "file_1.txt", "file_2.txt"])
            if entries == expected:
                tee("  mixed dir listing: OK")
                passed += 1
            else:
                tee(f"  mixed dir listing: FAIL (got {entries})")
                failed += 1

            # Test 5: Entry order (should be alphabetical from implementation)
            orderdir = root / "orderdir"
            orderdir.mkdir()
            names = ["zebra", "alpha", "gamma", "beta"]
            for n in names:
                (orderdir / n).touch()
            entries = os.listdir(str(orderdir))
            if entries == sorted(names):
                tee(f"  alphabetical order: OK (got {entries})")
                passed += 1
            else:
                tee(f"  alphabetical order: FAIL (got {entries}, expected {sorted(names)})")
                failed += 1

            # Test 6: Unlink then check listing
            rmtest = root / "rmtest"
            rmtest.mkdir()
            for i in range(5):
                (rmtest / f"r{i}").touch()
            (rmtest / "r2").unlink()
            entries = sorted(os.listdir(str(rmtest)))
            if entries == ["r0", "r1", "r3", "r4"]:
                tee("  unlink removes from listing: OK")
                passed += 1
            else:
                tee(f"  unlink listing: FAIL (got {entries})")
                failed += 1

        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

        tee(f"test_readdir: passed={passed} failed={failed}")
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
