#!/usr/bin/env python3
from __future__ import annotations

import errno
import os
import shutil
import stat
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
    root = mountpoint / f".agentfs-semantics-{os.getpid()}"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    try:
        file_path = root / "file.bin"
        fd = os.open(file_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)
        try:
            assert os.write(fd, b"abcdef") == 6
            os.fsync(fd)
            os.lseek(fd, 2, os.SEEK_SET)
            assert os.read(fd, 3) == b"cde"
        finally:
            os.close(fd)

        assert file_path.read_bytes() == b"abcdef"
        os.truncate(file_path, 3)
        assert file_path.read_bytes() == b"abc"
        os.truncate(file_path, 6)
        assert file_path.stat().st_size == 6

        os.chmod(file_path, 0o600)
        assert stat.S_IMODE(file_path.stat().st_mode) == 0o600

        renamed = root / "renamed.bin"
        os.rename(file_path, renamed)
        assert renamed.exists()
        assert not file_path.exists()

        nested = root / "dir"
        nested.mkdir()
        child = nested / "child.txt"
        child.write_text("child", encoding="utf-8")
        require_errno(lambda: nested.rmdir(), errno.ENOTEMPTY)
        assert sorted(p.name for p in root.iterdir()) == ["dir", "renamed.bin"]
        child.unlink()
        nested.rmdir()
        renamed.unlink()

        require_errno(lambda: (root / "missing").read_bytes(), errno.ENOENT)
        print("posix_semantics: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
