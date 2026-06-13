#!/usr/bin/env bash
# POSIX smoke test - full correctness tests for filesystem operations.
# Tests: mkdir, symlink, readlink, file create/write/read/truncate, rename,
#         chmod, utimens, unlink, rmdir, ENOTEMPTY, ENOENT.
set -euo pipefail
MOUNTPOINT="/mnt/agentfs"
ROOT="$MOUNTPOINT/.agentfs-smoke-$$"
LOG="/workspace/logs/tests/posix_smoke.log"

exec >"$LOG" 2>&1

echo "=== POSIX Smoke Test ==="
echo "MOUNTPOINT=$MOUNTPOINT"
echo "date=$(date -u)"

test -d "$MOUNTPOINT" || { echo "FAIL: mountpoint not a directory"; exit 1; }
test -w "$MOUNTPOINT" || { echo "FAIL: mountpoint not writable"; exit 1; }

mkdir -p "$ROOT"
trap 'rm -rf "$ROOT"' EXIT

PASSED=0
FAILED=0
TOTAL=0

check() {
    local desc="$1"; shift
    TOTAL=$((TOTAL+1))
    if "$@"; then
        echo "OK $TOTAL: $desc"
        PASSED=$((PASSED+1))
    else
        echo "FAIL $TOTAL: $desc"
        FAILED=$((FAILED+1))
    fi
}

# Test 1: mkdir
check "mkdir" mkdir "$ROOT/d"

# Test 2: symlink creation and readlink
check "symlink" ln -sf "target-string" "$ROOT/sym1"
check "readlink" test "$(readlink "$ROOT/sym1")" = "target-string"

# Test 3: unlink symlink
rm "$ROOT/sym1"
check "unlink symlink" test ! -e "$ROOT/sym1"

# Test 4: create regular file and write to it
echo "hello" > "$ROOT/a.txt"
check "file create/write" test -f "$ROOT/a.txt"

# Test 5: file content correct
check "file read" test "$(cat "$ROOT/a.txt")" = "hello"

# Test 6: file is regular (not symlink)
check "file is regular" test -f "$ROOT/a.txt" -a ! -L "$ROOT/a.txt"

# Test 7: append to file
echo "world" >> "$ROOT/a.txt"
check "file append" test "$(cat "$ROOT/a.txt")" = "$(printf 'hello\nworld\n')"

# Test 8: truncate file
truncate -s 5 "$ROOT/a.txt"
check "truncate" test "$(cat "$ROOT/a.txt")" = "hello"

# Test 9: rename file
check "rename" mv "$ROOT/a.txt" "$ROOT/b.txt"
check "renamed exists" test -f "$ROOT/b.txt"
check "old name gone" test ! -e "$ROOT/a.txt"

# Test 10: unlink file
rm "$ROOT/b.txt"
check "unlink file" test ! -e "$ROOT/b.txt"

# Test 11: rmdir
check "rmdir" rmdir "$ROOT/d"
check "rmdir gone" test ! -e "$ROOT/d"

# Test 12: ENOTEMPTY on non-empty dir
mkdir "$ROOT/d2"
echo "nested" > "$ROOT/d2/nested"
check "nested file" test -f "$ROOT/d2/nested"
rmdir "$ROOT/d2" 2>/dev/null && { echo "FAIL: rmdir non-empty succeeded (should fail)"; FAILED=$((FAILED+1)); TOTAL=$((TOTAL+1)); true; }
check "ENOTEMPTY" test -d "$ROOT/d2"
rm "$ROOT/d2/nested"
rmdir "$ROOT/d2"

# Test 13: chmod
echo "chmod_test" > "$ROOT/c.txt"
check "chmod 600" chmod 600 "$ROOT/c.txt"
PERMS=$(stat -c '%a' "$ROOT/c.txt" 2>/dev/null)
check "chmod 600 verified" test "$PERMS" = "600"
rm "$ROOT/c.txt"

# Test 14: utimens updates mtime
echo "utimens_test" > "$ROOT/dm.txt"
BEFORE=$(stat -c '%Y' "$ROOT/dm.txt" 2>/dev/null)
sleep 1
touch "$ROOT/dm.txt"
AFTER=$(stat -c '%Y' "$ROOT/dm.txt" 2>/dev/null)
check "utimens updates mtime" test "$BEFORE" != "$AFTER"
rm "$ROOT/dm.txt"

# Test 15: nested symlink readlink
mkdir "$ROOT/d3"
ln -sf "deep-target" "$ROOT/d3/deeplink"
check "nested symlink readlink" test "$(readlink "$ROOT/d3/deeplink")" = "deep-target"
rm "$ROOT/d3/deeplink"
rmdir "$ROOT/d3"

# Test 16: write/read large data (4KB)
dd if=/dev/urandom bs=4096 count=1 of=/tmp/.smoke-tmp-$$ 2>/dev/null
cp /tmp/.smoke-tmp-$$ "$ROOT/large.bin" 2>/dev/null
SIZE_BEFORE=$(stat -c '%s' "$ROOT/large.bin")
check "large file write" test "$SIZE_BEFORE" = "4096"
CMP=$(cmp /tmp/.smoke-tmp-$$ "$ROOT/large.bin" 2>&1 && echo "ok" || echo "fail")
check "large file content matches" test "$CMP" = "ok"
rm "$ROOT/large.bin"
rm /tmp/.smoke-tmp-$$

# Test 17: rename across directories
mkdir "$ROOT/d4"
mkdir "$ROOT/d5"
echo "cross-dir" > "$ROOT/d4/xfile"
check "cross-dir rename" mv "$ROOT/d4/xfile" "$ROOT/d5/xfile"
check "cross-dir dst exists" test -f "$ROOT/d5/xfile"
check "cross-dir src gone" test ! -e "$ROOT/d4/xfile"
rm "$ROOT/d5/xfile"
rmdir "$ROOT/d4"
rmdir "$ROOT/d5"

# Test 18: overwrite file in rename
echo "replace-me" > "$ROOT/r1.txt"
echo "replacement" > "$ROOT/r2.txt"
check "rename overwrite" mv "$ROOT/r2.txt" "$ROOT/r1.txt"
check "overwrite content" test "$(cat "$ROOT/r1.txt")" = "replacement"
check "old filename gone" test ! -e "$ROOT/r2.txt"
rm "$ROOT/r1.txt"

echo ""
echo "=== Results ==="
echo "passed=$PASSED failed=$FAILED total=$TOTAL"
if [ "$FAILED" -gt 0 ]; then
    echo "posix_smoke: FAILED"
    exit 1
else
    echo "posix_smoke: passed"
    exit 0
fi
