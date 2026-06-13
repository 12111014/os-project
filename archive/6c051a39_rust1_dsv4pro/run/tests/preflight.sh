#!/usr/bin/env bash
set -euo pipefail
MOUNTPOINT="/mnt/agentfs"
LOG="/workspace/logs/tests/preflight.log"

exec >"$LOG" 2>&1

echo "=== preflight checks ==="
echo "MOUNTPOINT=$MOUNTPOINT"
echo "date=$(date -u)"

# 1. Mount exists
echo "--- mount check ---"
mount | grep "$MOUNTPOINT" || { echo "FAIL: mount not found"; exit 1; }

# 2. Stat root
echo "--- stat root ---"
stat "$MOUNTPOINT" || { echo "FAIL: cannot stat root"; exit 1; }

# 3. df reports
echo "--- df ---"
df -hT "$MOUNTPOINT" || { echo "FAIL: df failed"; exit 1; }

# 4. readdir works
echo "--- ls root ---"
ls -la "$MOUNTPOINT" || { echo "FAIL: ls root failed"; exit 1; }

# 5. mkdir works
echo "--- mkdir test ---"
TESTDIR="$MOUNTPOINT/.preflight-$$"
mkdir "$TESTDIR" 2>/dev/null && rmdir "$TESTDIR" || { echo "FAIL: mkdir/rmdir failed"; exit 1; }

# 6. File create/write/read/unlink
echo "--- file create/write/read/unlink ---"
FILE="$MOUNTPOINT/.preflight-file-$$"
echo "hello_preflight" > "$FILE" 2>/dev/null || { echo "FAIL: write failed"; exit 1; }
CONTENT=$(cat "$FILE" 2>/dev/null)
if [ "$CONTENT" != "hello_preflight" ]; then
    echo "FAIL: read mismatch: got '$CONTENT'"
    exit 1
fi
rm "$FILE" 2>/dev/null || { echo "FAIL: unlink failed"; exit 1; }

# 7. symlink create/readlink/unlink
echo "--- symlink test ---"
SYM="$MOUNTPOINT/.preflight-sym-$$"
ln -sf "preflight-target" "$SYM" 2>/dev/null || { echo "FAIL: symlink create failed"; exit 1; }
SYMTGT=$(readlink "$SYM" 2>/dev/null)
if [ "$SYMTGT" != "preflight-target" ]; then
    echo "FAIL: symlink read mismatch: got '$SYMTGT'"
    exit 1
fi
rm "$SYM" 2>/dev/null || { echo "FAIL: symlink unlink failed"; exit 1; }

# 8. Check correct file type for regular files
echo "--- file type check ---"
RFILE="$MOUNTPOINT/.preflight-regfile-$$"
echo "data" > "$RFILE"
if [ -f "$RFILE" ] && [ ! -L "$RFILE" ]; then
    echo "OK: regular files are regular files (not symlinks)"
else
    echo "BUG: regular files appear as symlinks or something else"
    stat "$RFILE"
fi
rm "$RFILE"

echo ""
echo "preflight: PASSED"
