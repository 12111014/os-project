#!/usr/bin/env python3
"""Extended truncate tests"""
import os, shutil, sys
from pathlib import Path

def main() -> int:
    mount = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    root = mount / f".ext-trunc-{os.getpid()}"
    root.mkdir()
    try:
        f = root / "file.bin"
        # Write initial data
        f.write_bytes(b"0123456789")
        assert f.stat().st_size == 10

        # Truncate to smaller size
        os.truncate(str(f), 3)
        assert f.stat().st_size == 3
        assert f.read_bytes() == b"012"

        # Truncate to larger size (should zero-fill or at least change size)
        os.truncate(str(f), 10)
        assert f.stat().st_size == 10

        # Truncate to 0
        os.truncate(str(f), 0)
        assert f.stat().st_size == 0
        assert f.read_bytes() == b""

        # Truncate empty file to non-zero
        os.truncate(str(f), 5)
        assert f.stat().st_size == 5

        # Truncate on nonexistent
        try:
            os.truncate(str(root / "nonexistent"), 10)
            print("FAIL: truncate on nonexistent should fail")
            return 1
        except OSError as e:
            if e.errno != 2:
                print(f"FAIL: truncate on nonexistent got errno {e.errno}")
                return 1

        # Truncate via open file descriptor
        fd = os.open(str(f), os.O_RDWR)
        os.ftruncate(fd, 100)
        assert f.stat().st_size == 100
        os.close(fd)

        print("extended_truncate: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(main())
