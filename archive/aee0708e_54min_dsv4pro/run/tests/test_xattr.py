#!/usr/bin/env python3
"""Dedicated xattr tests (setxattr, getxattr, listxattr, removexattr)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

MOUNTPOINT = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
LOG = Path("/workspace/logs/tests/test_xattr.log")


def main() -> int:
    with open(LOG, "w") as log:
        def tee(msg):
            print(msg)
            log.write(msg + "\n")

        tee("=== test_xattr started ===")
        pid = os.getpid()
        root = MOUNTPOINT / f".test_xattr-{pid}"
        if root.exists():
            import shutil
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir()
        passed = 0
        failed = 0

        try:
            f = root / "file.txt"
            f.write_text("xattr test file")

            # Test 1: setxattr
            try:
                os.setxattr(str(f), "user.test_key", b"test_value")
                tee("  setxattr: OK")
                passed += 1
            except Exception as e:
                tee(f"  setxattr: FAIL - {e}")
                failed += 1

            # Test 2: getxattr
            try:
                val = os.getxattr(str(f), "user.test_key")
                if val == b"test_value":
                    tee("  getxattr: OK")
                    passed += 1
                else:
                    tee(f"  getxattr wrong value: FAIL (got {val})")
                    failed += 1
            except Exception as e:
                tee(f"  getxattr: FAIL - {e}")
                failed += 1

            # Test 3: listxattr
            try:
                attrs = os.listxattr(str(f))
                if "user.test_key" in attrs:
                    tee(f"  listxattr: OK (attrs={attrs})")
                    passed += 1
                else:
                    tee(f"  listxattr missing key: FAIL (attrs={attrs})")
                    failed += 1
            except Exception as e:
                tee(f"  listxattr: FAIL - {e}")
                failed += 1

            # Test 4: removexattr
            try:
                os.removexattr(str(f), "user.test_key")
                tee("  removexattr: OK")
                passed += 1
            except Exception as e:
                tee(f"  removexattr: FAIL - {e}")
                failed += 1

            # Test 5: getxattr after remove should fail
            try:
                os.getxattr(str(f), "user.test_key")
                tee("  getxattr after remove: FAIL (should error)")
                failed += 1
            except OSError:
                tee("  getxattr after remove (ENODATA): OK")
                passed += 1
            except Exception as e:
                tee(f"  getxattr after remove unexpected error: FAIL - {e}")
                failed += 1

            # Test 6: listxattr after remove
            try:
                attrs = os.listxattr(str(f))
                if "user.test_key" not in attrs:
                    tee(f"  listxattr after remove: OK (attrs={attrs})")
                    passed += 1
                else:
                    tee(f"  listxattr after remove still has key: FAIL")
                    failed += 1
            except Exception as e:
                tee(f"  listxattr after remove: FAIL - {e}")
                failed += 1

            # Test 7: setxattr on directory
            d = root / "subdir"
            d.mkdir()
            try:
                os.setxattr(str(d), "user.dir_attr", b"dir_val")
                val = os.getxattr(str(d), "user.dir_attr")
                if val == b"dir_val":
                    tee("  xattr on directory: OK")
                    passed += 1
                else:
                    tee("  xattr on directory wrong value: FAIL")
                    failed += 1
            except Exception as e:
                tee(f"  xattr on directory: FAIL - {e}")
                failed += 1

            # Test 8: Multiple xattrs
            f2 = root / "multi.txt"
            f2.write_text("multi")
            try:
                os.setxattr(str(f2), "user.a", b"1")
                os.setxattr(str(f2), "user.b", b"2")
                os.setxattr(str(f2), "user.c", b"3")
                attrs = sorted(os.listxattr(str(f2)))
                if attrs == ["user.a", "user.b", "user.c"]:
                    tee("  multiple xattrs: OK")
                    passed += 1
                else:
                    tee(f"  multiple xattrs wrong list: FAIL (got {attrs})")
                    failed += 1
            except Exception as e:
                tee(f"  multiple xattrs: FAIL - {e}")
                failed += 1

            # Test 9: Large xattr value
            large_val = b"x" * 4096
            try:
                os.setxattr(str(f), "user.large", large_val)
                val = os.getxattr(str(f), "user.large")
                if val == large_val:
                    tee(f"  large xattr ({len(large_val)} bytes): OK")
                    passed += 1
                else:
                    tee("  large xattr wrong value: FAIL")
                    failed += 1
            except Exception as e:
                tee(f"  large xattr: FAIL - {e}")
                failed += 1

        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

        tee(f"test_xattr: passed={passed} failed={failed}")
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
