#!/usr/bin/env bash
set -euo pipefail

MOUNTPOINT=${MOUNTPOINT:-/mnt/agentfs}
ROOT="$MOUNTPOINT/.bench-dd-$$"
mkdir -p "$ROOT"
trap 'rm -rf "$ROOT"' EXIT

echo "--- Sequential write (1MB) ---"
dd if=/dev/zero of="$ROOT/seq_write.bin" bs=1M count=10 2>&1

echo "--- Sequential read (1MB) ---"
dd if="$ROOT/seq_write.bin" of=/dev/null bs=1M count=10 2>&1

echo "--- Random write (4K blocks, 1000 ops) ---"
python3 - "$ROOT" <<'PYEOF'
import os, sys, time, random
root = sys.argv[1]
path = os.path.join(root, "rand.bin")
# Create file
with open(path, 'wb') as f:
    f.write(b'\x00' * 4096 * 1000)

data = os.urandom(4096)
start = time.monotonic()
fd = os.open(path, os.O_RDWR)
for _ in range(1000):
    offset = random.randint(0, 999) * 4096
    os.lseek(fd, offset, os.SEEK_SET)
    os.write(fd, data)
os.close(fd)
elapsed = time.monotonic() - start
print(f"random_4k_writes=1000 elapsed_sec={elapsed:.3f} iops={1000/elapsed:.1f}")
PYEOF

echo "--- Random read (4K blocks, 1000 ops) ---"
python3 - "$ROOT" <<'PYEOF'
import os, sys, time, random
root = sys.argv[1]
path = os.path.join(root, "rand.bin")
start = time.monotonic()
fd = os.open(path, os.O_RDONLY)
for _ in range(1000):
    offset = random.randint(0, 999) * 4096
    os.lseek(fd, offset, os.SEEK_SET)
    os.read(fd, 4096)
os.close(fd)
elapsed = time.monotonic() - start
print(f"random_4k_reads=1000 elapsed_sec={elapsed:.3f} iops={1000/elapsed:.1f}")
PYEOF

echo "--- Metadata ops (create+unlink 1000 files) ---"
python3 - "$ROOT" <<'PYEOF'
import os, time
root = sys.argv[1]
start = time.monotonic()
for i in range(1000):
    path = os.path.join(root, f"meta_{i}.txt")
    with open(path, 'w') as f:
        f.write(f"file{i}")
    os.unlink(path)
elapsed = time.monotonic() - start
print(f"metadata_create_unlink=1000 elapsed_sec={elapsed:.3f} ops_per_sec={1000/elapsed:.1f}")
PYEOF

echo "bench_dd: complete"
