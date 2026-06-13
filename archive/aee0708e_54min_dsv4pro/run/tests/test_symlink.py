#!/usr/bin/env python3
"""Dedicated symlink & readlink tests as per fs_ir."""
from __future__ import annotations

import errno
import os
import stat
import sys
from pathlib import Path


MOUNTPOINT = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
LOG = Path("/workspace/logs/tests/test_symlink.log")


def tee(log, msg):
    print(msg)
    log.write(msg + "\n")


def main() -> int:
    with open(LOG, "w") as log:
        tee(log, "=== test_symlink started ===")
        pid = os.getpid()
        root = MOUNTPOINT / f".test_symlink-{pid}"
        if root.exists():
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        passed = 0
        failed = 0

        try:
            # Test 1: Create file and relative symlink
            src = root / "src.txt"
            src.write_text("hello symlink")
            link = root / "link.txt"

            try:
                os.symlink("src.txt", str(link))
                tee(log, "  symlink create (relative): OK")
                passed += 1
            except Exception as e:
                tee(log, f"  symlink create (relative): FAIL - {e}")
                failed += 1

            # Test 2: readlink
            if link.exists(follow_symlinks=False) or link.is_symlink():
                try:
                    target = os.readlink(str(link))
                    tee(log, f"  readlink: target='{target}'")
                    if target == "src.txt":
                        tee(log, "  readlink correct: OK")
                        passed += 1
                    else:
                        tee(log, f"  readlink wrong target: FAIL (expected src.txt, got {target})")
                        failed += 1
                except Exception as e:
                    tee(log, f"  readlink: FAIL - {e}")
                    failed += 1
            else:
                # The symlink might be broken
                s = link.lstat()
                if stat.S_ISLNK(s.st_mode):
                    try:
                        target = os.readlink(str(link))
                        tee(log, f"  broken symlink readlink: target='{target}'")
                        passed += 1
                    except Exception as e:
                        tee(log, f"  readlink on broken symlink: FAIL - {e}")
                        failed += 1
                elif stat.S_ISREG(s.st_mode):
                    tee(log, "  symlink became regular file (BUG): FAIL")
                    failed += 1
                else:
                    tee(log, f"  unexpected file mode {s.st_mode:o}: FAIL")
                    failed += 1

            # Test 3: Read through symlink
            try:
                content = link.read_text()
                if content == "hello symlink":
                    tee(log, "  read through symlink: OK")
                    passed += 1
                else:
                    tee(log, f"  read through symlink wrong content: FAIL (got {content})")
                    failed += 1
            except Exception as e:
                tee(log, f"  read through symlink: FAIL - {e}")
                failed += 1

            # Test 4: Absolute symlink
            abs_link = root / "abs_link.txt"
            try:
                os.symlink(str(src), str(abs_link))
                tee(log, "  symlink create (absolute): OK")
                passed += 1
            except Exception as e:
                tee(log, f"  symlink create (absolute): FAIL - {e}")
                failed += 1

            # Test 5: Symlink chain depth
            chain_base = root / "chain0.txt"
            chain_base.write_text("chain test")
            prev = "chain0.txt"
            try:
                for i in range(5):
                    link_name = root / f"chain{i+1}.txt"
                    os.symlink(prev, str(link_name))
                    prev = f"chain{i+1}.txt"
                final = root / "chain5.txt"
                content = final.read_text()
                if content == "chain test":
                    tee(log, "  symlink chain (depth 5): OK")
                    passed += 1
                else:
                    tee(log, f"  symlink chain wrong content: FAIL")
                    failed += 1
            except Exception as e:
                tee(log, f"  symlink chain: FAIL - {e}")
                failed += 1

            # Test 6: Readlink on regular file should error
            try:
                os.readlink(str(src))
                tee(log, "  readlink on regular file: FAIL (should error)")
                failed += 1
            except OSError as e:
                if e.errno == errno.EINVAL:
                    tee(log, "  readlink on regular file (EINVAL): OK")
                    passed += 1
                else:
                    tee(log, f"  readlink on regular file wrong errno: FAIL (got {e.errno})")
                    failed += 1

            # Test 7: lstat on symlink
            if link.exists(follow_symlinks=False) or True:
                try:
                    s = link.lstat()
                    if stat.S_ISLNK(s.st_mode):
                        tee(log, f"  lstat on symlink (islink=True): OK")
                        passed += 1
                    elif stat.S_ISREG(s.st_mode):
                        tee(log, "  lstat on symlink: FAIL (should be LNK, got REG)")
                        failed += 1
                    else:
                        tee(log, f"  lstat on symlink unexpected mode {s.st_mode:o}: FAIL")
                        failed += 1
                except Exception as e:
                    tee(log, f"  lstat on symlink: FAIL - {e}")
                    failed += 1

            # Test 8: ELOOP detection
            loop1 = root / "loop1.txt"
            loop2 = root / "loop2.txt"
            try:
                os.symlink("loop1.txt", str(loop2))
                os.symlink("loop2.txt", str(loop1))
                try:
                    loop1.read_text()
                    tee(log, "  ELOOP detection: FAIL (should error)")
                    failed += 1
                except OSError as e:
                    if e.errno == errno.ELOOP:
                        tee(log, "  ELOOP detection: OK")
                        passed += 1
                    else:
                        tee(log, f"  ELOOP detection wrong errno: FAIL (got {e.errno})")
                        failed += 1
            except Exception as e:
                tee(log, f"  ELOOP setup failed: {e}")
                failed += 1

        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

        tee(log, f"test_symlink: passed={passed} failed={failed}")
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
