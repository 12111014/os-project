#!/usr/bin/env python3
"""Extended xattr tests based on fs_ir: getxattr, setxattr, listxattr, removexattr"""
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
    root = mount / f".ext-xattr-{os.getpid()}"
    root.mkdir()
    try:
        f = root / "file.txt"
        f.write_bytes(b"xattr test content")

        # setxattr / getxattr
        os.setxattr(str(f), "user.key1", b"val1")
        assert os.getxattr(str(f), "user.key1") == b"val1"

        # listxattr
        lst = os.listxattr(str(f))
        assert "user.key1" in lst

        # multiple xattrs
        os.setxattr(str(f), "user.key2", b"val2")
        lst2 = os.listxattr(str(f))
        assert "user.key1" in lst2 and "user.key2" in lst2

        # removexattr
        os.removexattr(str(f), "user.key1")
        lst3 = os.listxattr(str(f))
        assert "user.key1" not in lst3
        assert "user.key2" in lst3

        # removexattr on nonexistent should fail with ENODATA
        require_errno(lambda: os.removexattr(str(f), "user.nonexistent"), errno.ENODATA)

        # getxattr on nonexistent should fail
        require_errno(lambda: os.getxattr(str(f), "user.nonexistent"), errno.ENODATA)

        # xattr on directory
        os.setxattr(str(root), "user.dirattr", b"dirvalue")
        assert os.getxattr(str(root), "user.dirattr") == b"dirvalue"
        os.removexattr(str(root), "user.dirattr")

        print("extended_xattr: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(main())
