#!/usr/bin/env python3
"""Extended symlink tests: symlink, readlink, read-through-symlink, rename-over-symlink"""
from __future__ import annotations
import os, errno, shutil, sys
from pathlib import Path

def require_errno(fn, expected: int) -> None:
    try:
        fn()
    except OSError as exc:
        if exc.errno == expected:
            return
        raise AssertionError(f"expected errno {expected}, got {exc.errno}") from exc
    raise AssertionError(f"expected errno {expected}, got success")

def main() -> int:
    mount = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    root = mount / f".ext-symlink-{os.getpid()}"
    root.mkdir()
    try:
        # Create a target file
        target = root / "target.txt"
        target.write_bytes(b"symlink target content")

        # Create symlink to target using relative path
        link = root / "link.txt"
        os.symlink("target.txt", str(link))

        # readlink
        assert os.readlink(str(link)) == "target.txt"

        # Read through symlink
        assert link.read_bytes() == b"symlink target content"

        # Symlink to absolute path
        abs_link = root / "abs_link.txt"
        os.symlink(str(target), str(abs_link))
        assert abs_link.read_bytes() == b"symlink target content"

        # Symlink chain (link -> link -> target)
        chain1 = root / "chain1.txt"
        os.symlink("link.txt", str(chain1))
        assert chain1.read_bytes() == b"symlink target content"

        # Symlink to non-existent target
        broken = root / "broken.txt"
        os.symlink("nonexistent", str(broken))
        assert os.readlink(str(broken)) == "nonexistent"
        require_errno(lambda: broken.read_bytes(), errno.ENOENT)

        # Rename symlink target - symlink should follow
        new_target = root / "new_target.txt"
        os.rename(str(target), str(new_target))
        # The relative symlink "target.txt" is now broken since target was renamed
        require_errno(lambda: link.read_bytes(), errno.ENOENT)

        # Remove symlink with unlink
        os.unlink(str(link))
        os.unlink(str(abs_link))
        os.unlink(str(chain1))
        os.unlink(str(broken))
        os.unlink(str(new_target))

        print("extended_symlink: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(main())
