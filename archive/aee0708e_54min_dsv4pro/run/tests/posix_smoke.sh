#!/usr/bin/env bash
set -euo pipefail

MOUNTPOINT=${MOUNTPOINT:-/mnt/agentfs}
ROOT="$MOUNTPOINT/.agentfs-smoke-$$"

test -d "$MOUNTPOINT"
test -w "$MOUNTPOINT"
mkdir -p "$ROOT"
trap 'rm -rf "$ROOT"' EXIT

printf 'hello' > "$ROOT/a.txt"
test "$(cat "$ROOT/a.txt")" = "hello"

mkdir "$ROOT/d"
printf 'world' > "$ROOT/d/b.txt"
test "$(cat "$ROOT/d/b.txt")" = "world"

mv "$ROOT/d/b.txt" "$ROOT/c.txt"
test "$(cat "$ROOT/c.txt")" = "world"

truncate -s 2 "$ROOT/c.txt"
test "$(cat "$ROOT/c.txt")" = "wo"

chmod 600 "$ROOT/c.txt"
test -f "$ROOT/c.txt"

rm "$ROOT/a.txt"
rm "$ROOT/c.txt"
rmdir "$ROOT/d"
test -z "$(find "$ROOT" -mindepth 1 -maxdepth 1)"

echo "posix_smoke: passed"
