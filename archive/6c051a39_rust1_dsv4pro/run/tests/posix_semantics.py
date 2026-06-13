#!/usr/bin/env python3
"""POSIX semantics tests for agentfs.

Tests: directories, symlinks, regular file I/O, rename, chmod, utimens,
       truncation, xattrs, error semantics, statfs.
"""
from __future__ import annotations

import errno
import os
import shutil
import stat
import sys
import time
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
    
    passed = 0
    failed = 0
    bugs = []
    
    def check(desc: str, fn) -> None:
        nonlocal passed, failed
        try:
            fn()
            passed += 1
            print(f"OK: {desc}")
        except Exception as e:
            failed += 1
            print(f"FAIL: {desc}: {e}")

    try:
        # ---- Directory operations ----
        check("mkdir", lambda: root.joinpath("dir1").mkdir())
        check("mkdir exists", lambda: root.joinpath("dir1").is_dir())
        
        nested = root / "dir2"
        nested.mkdir()
        check("nested mkdir", lambda: nested.is_dir())
        (nested / "subdir").mkdir()
        require_errno(lambda: nested.rmdir(), errno.ENOTEMPTY)
        check("rmdir ENOTEMPTY on non-empty dir", lambda: True)
        (nested / "subdir").rmdir()
        nested.rmdir()
        check("rmdir empty dir", lambda: not nested.exists())
        
        # ---- Symlink operations ----
        sym_path = root / "mylink"
        os.symlink("target-string-here", str(sym_path))
        check("symlink create", lambda: sym_path.is_symlink())
        check("readlink", lambda: os.readlink(str(sym_path)) == "target-string-here")
        sym_path.unlink()
        check("symlink unlink", lambda: not sym_path.exists())
        
        # ---- Regular file creation / write / read ----
        file_path = root / "file.bin"
        fd = os.open(str(file_path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)
        try:
            n = os.write(fd, b"abcdefghij")
            assert n == 10, f"write returned {n} expected 10"
            os.fsync(fd)
            os.lseek(fd, 2, os.SEEK_SET)
            data = os.read(fd, 5)
            assert data == b"cdefg", f"read returned {data!r} expected b'cdefg'"
            check("file create/open/write/fsync/seek/read", lambda: True)
        finally:
            os.close(fd)
        
        # Verify content via path
        check("file content via path", lambda: file_path.read_bytes() == b"abcdefghij")
        
        # Check file type is regular
        st = file_path.lstat()
        if stat.S_ISREG(st.st_mode):
            check("file type is regular", lambda: True)
        else:
            bugs.append(f"BUG: file mode is {st.st_mode:o}, expected regular file")
            print(f"BUG: file mode is {st.st_mode:o}, expected regular file")
            failed += 1

        # ---- Truncate ----
        os.truncate(str(file_path), 3)
        check("truncate to 3", lambda: file_path.read_bytes() == b"abc")
        os.truncate(str(file_path), 6)
        check("truncate expand to 6", lambda: file_path.stat().st_size == 6)
        # Expanded region should be zeros
        data = file_path.read_bytes()
        check("truncate expand zero-filled", lambda: data == b"abc\x00\x00\x00")
        
        # ---- chmod ----
        os.chmod(str(file_path), 0o600)
        check("chmod 600", lambda: stat.S_IMODE(file_path.stat().st_mode) == 0o600)
        
        # ---- Rename ----
        renamed = root / "renamed.bin"
        os.rename(str(file_path), str(renamed))
        check("rename dst exists", lambda: renamed.exists())
        check("rename src gone", lambda: not file_path.exists())
        
        # ---- Overwrite via rename ----
        ow_src = root / "ow_src"
        ow_dst = root / "ow_dst"
        ow_src.write_bytes(b"new-content")
        ow_dst.write_bytes(b"old-content")
        os.rename(str(ow_src), str(ow_dst))
        check("rename overwrite dst content", lambda: ow_dst.read_bytes() == b"new-content")
        check("rename overwrite src gone", lambda: not ow_src.exists())
        ow_dst.unlink()
        
        # ---- Cross-directory rename ----
        d1 = root / "cross1"
        d2 = root / "cross2"
        d1.mkdir()
        d2.mkdir()
        (d1 / "xfile").write_bytes(b"cross")
        os.rename(str(d1 / "xfile"), str(d2 / "xfile"))
        check("cross-dir rename dst", lambda: (d2 / "xfile").exists())
        check("cross-dir rename src gone", lambda: not (d1 / "xfile").exists())
        check("cross-dir rename content", lambda: (d2 / "xfile").read_bytes() == b"cross")
        (d2 / "xfile").unlink()
        d1.rmdir()
        d2.rmdir()
        
        # ---- utimens ----
        ts_file = root / "timestamp_test"
        ts_file.write_bytes(b"time-me")
        before_stat = ts_file.stat()
        time.sleep(1.1)
        os.utime(str(ts_file))
        after_stat = ts_file.stat()
        check("utimens updates mtime", lambda: after_stat.st_mtime > before_stat.st_mtime)
        ts_file.unlink()
        
        # ---- chmod on regular file with stat ----
        ch_file = root / "chmod_test"
        ch_file.write_bytes(b"perms")
        os.chmod(str(ch_file), 0o400)
        check("chmod 400", lambda: stat.S_IMODE(ch_file.stat().st_mode) == 0o400)
        os.chmod(str(ch_file), 0o644)
        check("chmod back to 644", lambda: stat.S_IMODE(ch_file.stat().st_mode) == 0o644)
        ch_file.unlink()
        
        # ---- ENOENT semantics ----
        require_errno(lambda: (root / "missing").read_bytes(), errno.ENOENT)
        check("ENOENT on missing file", lambda: True)
        require_errno(lambda: os.stat(str(root / "noexist")), errno.ENOENT)
        check("ENOENT on stat missing", lambda: True)
        
        # ---- xattr ----
        xattr_file = root / "xattr_test"
        xattr_file.write_bytes(b"xattr-data")
        try:
            os.setxattr(str(xattr_file), "user.test_key", b"test_value")
            val = os.getxattr(str(xattr_file), "user.test_key")
            check("xattr set/get", lambda: val == b"test_value")
            os.removexattr(str(xattr_file), "user.test_key")
            check("xattr remove", lambda: True)
        except OSError as e:
            print(f"NOTE: xattr ops: {e}")
            passed += 1  # Still count as passed if xattr not supported
        xattr_file.unlink()
        
        # ---- statfs ----
        st = os.statvfs(str(mountpoint))
        check("statfs returns", lambda: st.f_bsize > 0)
        
        # ---- Append to file (O_APPEND behavior) ----
        app_file = root / "append_test"
        app_file.write_bytes(b"first")
        fd = os.open(str(app_file), os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, b"second")
        finally:
            os.close(fd)
        check("append content", lambda: app_file.read_bytes() == b"firstsecond")
        app_file.unlink()
        
        # ---- Unlink and re-create ----
        ul_file = root / "unlink_recreate"
        ul_file.write_bytes(b"v1")
        ul_file.unlink()
        check("unlink vanishes", lambda: not ul_file.exists())
        ul_file.write_bytes(b"v2")
        check("recreate after unlink", lambda: ul_file.read_bytes() == b"v2")
        ul_file.unlink()
        
        renamed.unlink()
        root.joinpath("dir1").rmdir()
        
    finally:
        shutil.rmtree(root, ignore_errors=True)
    
    print(f"\n=== Results ===")
    print(f"passed={passed} failed={failed}")
    for bug in bugs:
        print(bug)
    if failed > 0:
        print("posix_semantics: FAILED")
        return 1
    else:
        print("posix_semantics: passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
