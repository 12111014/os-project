#!/usr/bin/env python3
"""Extended attribute (xattr) correctness tests."""
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
    root = mountpoint / f".agentfs-xattr-{os.getpid()}"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    try:
        fpath = root / "testfile.txt"
        fpath.write_text("content")

        # setxattr / getxattr
        os.setxattr(str(fpath), "user.testkey", b"testvalue")
        val = os.getxattr(str(fpath), "user.testkey")
        assert val == b"testvalue", f"getxattr: expected b'testvalue', got {val}"

        # listxattr
        attrs = os.listxattr(str(fpath))
        assert "user.testkey" in attrs, f"listxattr missing testkey: {attrs}"

        # removexattr
        os.removexattr(str(fpath), "user.testkey")
        require_errno(lambda: os.getxattr(str(fpath), "user.testkey"), errno.ENODATA)

        # getxattr on missing attr
        require_errno(lambda: os.getxattr(str(fpath), "user.nonexistent"), errno.ENODATA)

        # xattr on directory
        os.setxattr(str(root), "user.dirkey", b"dirvalue")
        val = os.getxattr(str(root), "user.dirkey")
        assert val == b"dirvalue"

        fpath.unlink()
        print("xattr_test: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
