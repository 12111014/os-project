#!/usr/bin/env bash
set -euo pipefail

MOUNTPOINT=${MOUNTPOINT:-/mnt/agentfs}
FILES=${FSMARK_FILES:-1000}
THREADS=${FSMARK_THREADS:-4}
BYTES=${FSMARK_BYTES:-4096}
ROOT="$MOUNTPOINT/.agentfs-fsmark-$$"
FSMARK=${FSMARK_BIN:-fs_mark}

mkdir -p "$ROOT"
trap 'rm -rf "$ROOT"' EXIT

if command -v "$FSMARK" >/dev/null 2>&1; then
  "$FSMARK" -d "$ROOT" -n "$FILES" -t "$THREADS" -s "$BYTES"
else
  python3 - "$ROOT" "$FILES" "$THREADS" "$BYTES" <<'PY'
import concurrent.futures
import pathlib
import sys
import time

root = pathlib.Path(sys.argv[1])
files = int(sys.argv[2])
threads = int(sys.argv[3])
size = int(sys.argv[4])
payload = b"x" * size

def create(index: int) -> None:
    path = root / f"f{index}"
    path.write_bytes(payload)
    path.unlink()

start = time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
    list(executor.map(create, range(files)))
elapsed = time.monotonic() - start
print(f"fs_mark_fallback files={files} threads={threads} elapsed_sec={elapsed:.3f} files_per_sec={files / elapsed:.2f}")
PY
fi
