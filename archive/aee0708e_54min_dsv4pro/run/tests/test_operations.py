#!/usr/bin/env python3
"""Comprehensive operation tests covering: create, open, read, write, truncate,
rename, mkdir, rmdir, unlink, chmod, fsync, getattr."""
from __future__ import annotations

import errno
import os
import stat
import sys
import time
from pathlib import Path

MOUNTPOINT = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
LOG = Path("/workspace/logs/tests/test_operations.log")


def main() -> int:
    with open(LOG, "w") as log:
        def tee(msg):
            print(msg)
            log.write(msg + "\n")

        tee("=== test_operations started ===")
        pid = os.getpid()
        root = MOUNTPOINT / f".test_ops-{pid}"
        if root.exists():
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        passed = 0
        failed = 0

        try:
            # --- CREATE / OPEN / WRITE / READ ---
            tee("-- create/open/write/read --")
            f = root / "data.bin"
            fd = os.open(str(f), os.O_CREAT | os.O_RDWR, 0o644)
            try:
                n = os.write(fd, b"Hello, FUSE world!")
                if n == 18:
                    tee("  write: OK")
                    passed += 1
                else:
                    tee(f"  write: FAIL (wrote {n} bytes)")
                    failed += 1

                os.lseek(fd, 0, os.SEEK_SET)
                data = os.read(fd, 18)
                if data == b"Hello, FUSE world!":
                    tee("  read: OK")
                    passed += 1
                else:
                    tee(f"  read: FAIL (got {data})")
                    failed += 1

                # PRead after seek
                os.lseek(fd, 7, os.SEEK_SET)
                data = os.read(fd, 4)
                if data == b"FUSE":
                    tee("  seek+read: OK")
                    passed += 1
                else:
                    tee(f"  seek+read: FAIL (got {data})")
                    failed += 1

                # Write at offset
                os.lseek(fd, 7, os.SEEK_SET)
                n = os.write(fd, b"fuse")
                if n == 4:
                    tee("  write at offset: OK")
                    passed += 1
                else:
                    tee(f"  write at offset: FAIL (wrote {n})")
                    failed += 1

                # Verify overwrite
                os.lseek(fd, 0, os.SEEK_SET)
                data = os.read(fd, 18)
                if data == b"Hello, fuse world!":
                    tee("  overwrite verify: OK")
                    passed += 1
                else:
                    tee(f"  overwrite verify: FAIL (got {data})")
                    failed += 1

                # FSYNC
                try:
                    os.fsync(fd)
                    tee("  fsync: OK")
                    passed += 1
                except Exception as e:
                    tee(f"  fsync: FAIL - {e}")
                    failed += 1

            finally:
                os.close(fd)

            # --- TRUNCATE ---
            tee("-- truncate --")
            os.truncate(str(f), 5)
            s = f.stat()
            if s.st_size == 5:
                tee("  truncate size: OK")
                passed += 1
            else:
                tee(f"  truncate size: FAIL (size={s.st_size})")
                failed += 1

            data = f.read_bytes()
            if data == b"Hello":
                tee("  truncate content: OK")
                passed += 1
            else:
                tee(f"  truncate content: FAIL (got {data})")
                failed += 1

            # Extend via truncate
            os.truncate(str(f), 10)
            s = f.stat()
            if s.st_size == 10:
                tee("  truncate extend size: OK")
                passed += 1
            else:
                tee(f"  truncate extend size: FAIL (size={s.st_size})")
                failed += 1

            # --- CHMOD ---
            tee("-- chmod --")
            os.chmod(str(f), 0o640)
            mode = stat.S_IMODE(f.stat().st_mode)
            if mode == 0o640:
                tee("  chmod: OK")
                passed += 1
            else:
                tee(f"  chmod: FAIL (mode={mode:o})")
                failed += 1

            # --- GETATTR ---
            tee("-- getattr --")
            s = f.stat()
            if s.st_ino > 0 and s.st_nlink > 0:
                tee(f"  getattr: OK (ino={s.st_ino}, nlink={s.st_nlink}, size={s.st_size})")
                passed += 1
            else:
                tee(f"  getattr: FAIL")
                failed += 1

            # --- RENAME ---
            tee("-- rename --")
            f2 = root / "renamed.bin"
            os.rename(str(f), str(f2))
            if f2.exists() and not f.exists():
                tee("  rename: OK")
                passed += 1
            else:
                tee("  rename: FAIL")
                failed += 1

            # --- MKDIR / RMDIR ---
            tee("-- mkdir/rmdir --")
            d = root / "testdir"
            d.mkdir(mode=0o755)
            if d.is_dir():
                tee("  mkdir: OK")
                passed += 1
            else:
                tee("  mkdir: FAIL")
                failed += 1

            # ENOTEMPTY check
            child = d / "child.txt"
            child.write_text("x")
            try:
                d.rmdir()
                tee("  rmdir non-empty: FAIL (should error)")
                failed += 1
            except OSError as e:
                if e.errno == errno.ENOTEMPTY:
                    tee("  rmdir non-empty (ENOTEMPTY): OK")
                    passed += 1
                else:
                    tee(f"  rmdir non-empty wrong errno: FAIL (got {e.errno})")
                    failed += 1

            child.unlink()
            d.rmdir()
            if not d.exists():
                tee("  rmdir: OK")
                passed += 1
            else:
                tee("  rmdir: FAIL")
                failed += 1

            # --- UNLINK ---
            tee("-- unlink --")
            uf = root / "todelete.txt"
            uf.write_text("delete me")
            uf.unlink()
            if not uf.exists():
                tee("  unlink: OK")
                passed += 1
            else:
                tee("  unlink: FAIL")
                failed += 1

            # --- ENOENT ---
            tee("-- error handling --")
            try:
                (root / "nonexistent").read_bytes()
                tee("  ENOENT on read: FAIL (should error)")
                failed += 1
            except FileNotFoundError:
                tee("  ENOENT on read: OK")
                passed += 1

            # EISDIR on write
            d2 = root / "adir"
            d2.mkdir()
            try:
                d2.write_text("bad")
                tee("  EISDIR on write: FAIL (should error)")
                failed += 1
            except IsADirectoryError:
                tee("  EISDIR on write: OK")
                passed += 1
            d2.rmdir()

            # EEXIST on mkdir
            d3 = root / "exists_dir"
            d3.mkdir()
            try:
                d3.mkdir()
                tee("  EEXIST on mkdir: FAIL (should error)")
                failed += 1
            except FileExistsError:
                tee("  EEXIST on mkdir: OK")
                passed += 1
            d3.rmdir()

            # --- Write beyond current size (append) ---
            tee("-- write append --")
            af = root / "append.txt"
            af.write_text("first")
            with open(str(af), "a") as afh:
                afh.write("second")
            data = af.read_text()
            if data == "firstsecond":
                tee("  write append: OK")
                passed += 1
            else:
                tee(f"  write append: FAIL (got {data})")
                failed += 1

            # --- Large write ---
            tee("-- large write --")
            lf = root / "large.bin"
            payload = b"A" * 65536  # 64KB
            lf.write_bytes(payload)
            data = lf.read_bytes()
            if len(data) == 65536 and data == payload:
                tee(f"  large write/read (64KB): OK")
                passed += 1
            else:
                tee(f"  large write/read: FAIL (len={len(data)})")
                failed += 1

            # --- Sparse file-like: seek past EOF and write ---
            tee("-- sparse write --")
            sf = root / "sparse.bin"
            fd = os.open(str(sf), os.O_CREAT | os.O_RDWR, 0o644)
            try:
                os.lseek(fd, 100, os.SEEK_SET)
                os.write(fd, b"END")
            finally:
                os.close(fd)
            s = sf.stat()
            if s.st_size == 103:
                tee(f"  sparse write size: OK ({s.st_size})")
                passed += 1
            else:
                tee(f"  sparse write size: FAIL ({s.st_size})")
                failed += 1

        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

        tee(f"test_operations: passed={passed} failed={failed}")
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
