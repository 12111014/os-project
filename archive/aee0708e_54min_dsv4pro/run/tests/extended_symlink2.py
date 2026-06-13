#!/usr/bin/env python3
"""Simplified symlink diagnostics"""
from __future__ import annotations
import os, sys
from pathlib import Path

mount = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
root = mount / f".ext-sym-{os.getpid()}"
root.mkdir()
print(f"root={root} exists={root.exists()}")

# Create target
target = root / "target.txt"
target.write_bytes(b"hello")
print(f"target={target} exists={target.exists()} size={target.stat().st_size}")

# Try symlink with different forms
tests = [
    ("absolute target", str(target), str(root / "link_abs.txt")),
    ("relative basename", "target.txt", str(root / "link_rel.txt")),
    ("relative ./", "./target.txt", str(root / "link_dot.txt")),
    ("relative ../", "../target.txt", str(root / "link_dotdot.txt")),
]

for desc, src, dst in tests:
    try:
        os.symlink(src, dst)
        print(f"  {desc}: OK src='{src}' dst='{dst}'")
        r = os.readlink(dst)
        print(f"    readlink={r}")
        try:
            data = open(dst, 'r').read()
            print(f"    read-through: '{data}'")
        except Exception as e:
            print(f"    read-through FAILED: {e}")
        os.unlink(dst)
    except OSError as e:
        print(f"  {desc}: FAILED errno={e.errno} msg={e}")

import shutil
shutil.rmtree(root, ignore_errors=True)
