#!/usr/bin/env python3
"""Extended chmod tests"""
import os, shutil, sys, stat
from pathlib import Path

def main() -> int:
    mount = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    root = mount / f".ext-chmod-{os.getpid()}"
    root.mkdir()
    try:
        f = root / "file.txt"
        f.write_bytes(b"content")

        # chmod to various modes
        for mode in [0o644, 0o600, 0o755, 0o400, 0o200, 0o100, 0o000]:
            os.chmod(str(f), mode)
            actual = stat.S_IMODE(f.stat().st_mode)
            if actual != mode:
                print(f"FAIL: chmod {oct(mode)} → got {oct(actual)}")
                return 1

        # chmod on directory
        d = root / "subdir"
        d.mkdir()
        os.chmod(str(d), 0o700)
        assert stat.S_IMODE(d.stat().st_mode) == 0o700

        # chmod on nonexistent
        try:
            os.chmod(str(root / "nonexistent"), 0o644)
            print("FAIL: chmod on nonexistent should fail")
            return 1
        except OSError as e:
            if e.errno != 2:  # ENOENT
                print(f"FAIL: chmod on nonexistent got errno {e.errno}, expected ENOENT(2)")
                return 1

        print("extended_chmod: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(main())
