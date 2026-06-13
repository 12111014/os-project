#!/usr/bin/env python3
"""Large I/O tests"""
import os, shutil, sys
from pathlib import Path

def main() -> int:
    mount = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    root = mount / f".ext-largeio-{os.getpid()}"
    root.mkdir()
    try:
        f = root / "large.bin"

        # Write 1MB of data
        data = b"A" * (1024 * 1024)
        f.write_bytes(data)
        assert f.stat().st_size == 1024 * 1024

        # Read it back and verify
        read_back = f.read_bytes()
        if read_back != data:
            print(f"FAIL: read back mismatch at size 1MB")
            return 1

        # Write at offset (partial overwrite)
        fd = os.open(str(f), os.O_RDWR)
        os.lseek(fd, 100, os.SEEK_SET)
        os.write(fd, b"BBBB")
        os.close(fd)
        content = f.read_bytes()
        assert content[100:104] == b"BBBB"
        assert content[0:100] == b"A" * 100
        assert content[104:] == b"A" * (1024 * 1024 - 104)

        # Append via write at end
        fd = os.open(str(f), os.O_RDWR | os.O_APPEND)
        os.write(fd, b"TAIL")
        os.close(fd)
        assert f.stat().st_size == 1024 * 1024 + 4
        content = f.read_bytes()
        assert content[-4:] == b"TAIL"

        print("extended_large_io: passed")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(main())
