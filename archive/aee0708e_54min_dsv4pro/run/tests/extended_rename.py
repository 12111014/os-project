#!/usr/bin/env python3
"""Extended rename tests"""
import os, shutil, sys
from pathlib import Path

def main() -> int:
    mount = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    root = mount / f".ext-rename-{os.getpid()}"
    root.mkdir()
    try:
        # Simple rename file
        src = root / "src.txt"
        dst = root / "dst.txt"
        src.write_bytes(b"rename test")
        os.rename(str(src), str(dst))
        assert not src.exists()
        assert dst.exists()
        assert dst.read_bytes() == b"rename test"

        # Rename directory
        d1 = root / "dir1"
        d2 = root / "dir2"
        d1.mkdir()
        (d1 / "inside.txt").write_bytes(b"inside")
        os.rename(str(d1), str(d2))
        assert not d1.exists()
        assert d2.exists()
        assert (d2 / "inside.txt").read_bytes() == b"inside"

        # Rename over existing file
        a = root / "a.txt"
        b = root / "b.txt"
        a.write_bytes(b"aaa")
        b.write_bytes(b"bbb")
        os.rename(str(a), str(b))
        assert not a.exists()
        assert b.exists()
        assert b.read_bytes() == b"aaa"

        # Rename over existing directory (should fail or succeed depending on semantics)
        d3 = root / "d3"
        d4 = root / "d4"
        d3.mkdir()
        d4.mkdir()
        try:
            os.rename(str(d3), str(d4))
            # If it succeeded, d3 should be gone and d4 replaced
            assert not d3.exists()
            assert d4.exists()
        except OSError as e:
            # Some implementations require target dir to be empty
            pass

        # Rename nonexistent source
        try:
            os.rename(str(root / "noexist"), str(root / "dst"))
            print("FAIL: rename nonexistent should fail")
            return 1
        except OSError as e:
            if e.errno != 2:
                print(f"FAIL: rename nonexistent got errno {e.errno}")
                return 1

        print("extended_rename: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(main())
