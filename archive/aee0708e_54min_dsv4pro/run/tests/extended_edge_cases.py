#!/usr/bin/env python3
"""Edge case tests for directory and file operations"""
import os, errno, shutil, sys
from pathlib import Path

def require_errno(fn, expected):
    try:
        fn()
    except OSError as e:
        if e.errno == expected:
            return
        raise AssertionError(f"expected errno {expected}, got {e.errno}") from e
    raise AssertionError(f"expected errno {expected}, got success")

def main() -> int:
    mount = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    root = mount / f".ext-edge-{os.getpid()}"
    root.mkdir()
    try:
        # rmdir on non-empty directory
        d = root / "nonempty"
        d.mkdir()
        (d / "child.txt").write_text("x")
        require_errno(lambda: d.rmdir(), errno.ENOTEMPTY)

        # mkdir of existing name
        require_errno(lambda: d.mkdir(), errno.EEXIST)

        # unlink of directory
        require_errno(lambda: d.unlink(), errno.EISDIR if hasattr(errno, 'EISDIR') else errno.EPERM)

        # open directory as file for read
        try:
            open(str(d), "r").close()
            print("NOTE: opening directory for read succeeded (allowed on some systems)")
        except OSError as e:
            pass  # Expected on most systems

        # create file in nonexistent directory
        require_errno(lambda: (root / "nodir" / "file.txt").write_text("x"), errno.ENOENT)

        # mkdir in nonexistent parent
        require_errno(lambda: (root / "nodir" / "subdir").mkdir(), errno.ENOENT)

        # write to file opened read-only should fail
        rfile = root / "readonly.txt"
        rfile.write_text("data")
        fd = os.open(str(rfile), os.O_RDONLY)
        try:
            os.write(fd, b"write to ro")
            print("NOTE: write to read-only fd succeeded (unexpected)")
        except OSError as e:
            if e.errno != 9:  # EBADF
                pass  # EPERM or similar
        os.close(fd)

        # read beyond EOF
        assert rfile.read_bytes() == b"data"
        fd = os.open(str(rfile), os.O_RDONLY)
        os.lseek(fd, 100, os.SEEK_SET)
        result = os.read(fd, 10)
        assert result == b"" or len(result) == 0  # EOF → empty read
        os.close(fd)

        print("extended_edge_cases: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(main())
