#!/usr/bin/env python3
"""Edge case correctness tests for FUSE filesystem."""
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
    root = mountpoint / f".agentfs-edge-{os.getpid()}"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir()
    try:
        # 1. Write past 4KB boundary (cross block)
        f = root / "cross_block.bin"
        data = b"A" * 4097
        f.write_bytes(data)
        assert f.stat().st_size == 4097
        assert f.read_bytes() == data

        # 2. Sparse file via truncate
        f2 = root / "sparse.bin"
        f2.write_bytes(b"")
        os.truncate(str(f2), 65536)
        st = f2.stat()
        assert st.st_size == 65536, f"sparse size: {st.st_size}"
        content = f2.read_bytes()
        assert content == b"\x00" * 65536, "sparse should read zeros"

        # 3. Zero-length file
        f3 = root / "zero.bin"
        f3.write_bytes(b"")
        assert f3.stat().st_size == 0
        assert f3.read_bytes() == b""

        # 4. Rename over existing file
        f4 = root / "old.bin"
        f5 = root / "new.bin"
        f4.write_text("old")
        f5.write_text("new")
        os.rename(str(f4), str(f5))
        assert not f4.exists()
        assert f5.read_text() == "old"

        # 5. Nested directories and deep path
        deep = root / "a" / "b" / "c"
        deep.mkdir(parents=True)
        deep_file = deep / "deep.txt"
        deep_file.write_text("deep")
        assert deep_file.read_text() == "deep"

        # 6. Rmdir non-existent
        require_errno(lambda: (root / "noexist").rmdir(), errno.ENOENT)

        # 7. Mkdir existing
        exist_dir = root / "exist"
        exist_dir.mkdir()
        require_errno(lambda: exist_dir.mkdir(), errno.EEXIST)
        exist_dir.rmdir()

        # 8. Chmod: verify mode bits are set correctly
        ro_file = root / "ro.bin"
        ro_file.write_text("readonly")
        os.chmod(str(ro_file), 0o400)
        mode = ro_file.stat().st_mode & 0o777
        assert mode == 0o400, f"chmod: expected 0o400, got {oct(mode)}"
        ro_file.unlink()

        # 9. Write and fsync
        fsync_file = root / "fsync.bin"
        fd = os.open(str(fsync_file), os.O_CREAT | os.O_RDWR, 0o644)
        os.write(fd, b"fsync data")
        os.fsync(fd)
        os.close(fd)
        assert fsync_file.read_bytes() == b"fsync data"
        fsync_file.unlink()

        # 10. Truncate to 0
        trunc_file = root / "trunc.bin"
        trunc_file.write_text("hello world")
        os.truncate(str(trunc_file), 0)
        assert trunc_file.stat().st_size == 0
        trunc_file.unlink()

        # 11. Create with O_EXCL
        excl = root / "excl.bin"
        fd = os.open(str(excl), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)
        os.close(fd)
        require_errno(lambda: os.open(str(excl), os.O_CREAT | os.O_EXCL), errno.EEXIST)
        excl.unlink()

        # 12. Large filename
        long_name = "x" * 200
        long_file = root / long_name
        long_file.write_text("long")
        assert long_file.exists()
        assert long_file.read_text() == "long"
        long_file.unlink()

        # 13. Truncate extending file (should zero-fill)
        ext_file = root / "extend.bin"
        ext_file.write_text("hi")
        os.truncate(str(ext_file), 10)
        assert ext_file.stat().st_size == 10
        data = ext_file.read_bytes()
        assert data[:2] == b"hi"
        assert data[2:] == b"\x00" * 8
        ext_file.unlink()

        # Cleanup deep dirs
        shutil.rmtree(str(root / "a"), ignore_errors=True)

        print("edge_case_test: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
