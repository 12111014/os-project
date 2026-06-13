#!/usr/bin/env python3
"""Symlink and readlink correctness tests."""
from __future__ import annotations

import errno
import os
import shutil
import sys
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
    mountpoint = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    root = mountpoint / f".agentfs-symlink-{os.getpid()}"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    try:
        # Create a target file
        target = root / "target.txt"
        target.write_text("symlink target content")

        # Create symlink
        link = root / "link.txt"
        os.symlink("target.txt", str(link))

        # readlink
        resolved = os.readlink(str(link))
        assert resolved == "target.txt", f"readlink: expected 'target.txt', got '{resolved}'"

        # Follow symlink to read
        content = link.read_text()
        assert content == "symlink target content", f"symlink read: bad content"

        # Follow symlink to stat
        st = link.lstat()
        assert st.st_size > 0, "lstat on symlink should return symlink stat"

        # Remove symlink and verify target still exists
        link.unlink()
        assert not link.exists()
        assert target.exists()
        assert target.read_text() == "symlink target content"

        # Symlink to directory
        subdir = root / "subdir"
        subdir.mkdir()
        dirlink = root / "dirlink"
        os.symlink("subdir", str(dirlink))
        assert dirlink.is_symlink()
        (dirlink / "nested.txt").write_text("nested")
        assert (subdir / "nested.txt").read_text() == "nested"
        (dirlink / "nested.txt").unlink()
        dirlink.unlink()
        subdir.rmdir()

        # Broken symlink
        broken = root / "broken"
        os.symlink("nonexistent", str(broken))
        require_errno(lambda: broken.read_text(), errno.ENOENT)
        broken.unlink()

        # Symlink in error cases
        require_errno(lambda: os.symlink("a", str(root / "missing_dir/x")), errno.ENOENT)

        print("symlink_test: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
