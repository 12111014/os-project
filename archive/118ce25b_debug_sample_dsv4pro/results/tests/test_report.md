# Test Report: agentfs FUSE Filesystem

**Date**: 2026-06-11  
**Mountpoint**: `/mnt/agentfs`  
**Filesystem**: agentfs (fuse.agentfs, libfuse3, in-memory backend)  
**Tester**: Automated Test Agent

---

## 1. Preflight Mount Checks

| Check | Status | Detail |
|-------|--------|--------|
| Mount exists | ✅ passed | `agentfs on /mnt/agentfs type fuse.agentfs (rw,nosuid,nodev,relatime,user_id=0,group_id=0,allow_other)` |
| Root directory accessible | ✅ passed | `drwxr-xr-x 2 root root` |
| Read-write accessible | ✅ passed | File create, read, delete OK |
| Directory create/remove | ✅ passed | mkdir/rmdir OK |
| Filesystem size reported | ✅ passed | `1.0G` total, 0 used |

---

## 2. Correctness Tests

### 2.1 posix_smoke (template) — ✅ passed
- **Suite**: correctness
- **Command**: `MOUNTPOINT=/mnt/agentfs bash posix_smoke.sh`
- **Log**: `/workspace/logs/tests/posix_smoke.log`
- **Summary**: Basic POSIX operations (create, write, read, mkdir, rename, truncate, chmod, unlink, rmdir) all working correctly.

### 2.2 posix_semantics (template) — ✅ passed
- **Suite**: correctness
- **Command**: `MOUNTPOINT=/mnt/agentfs python3 posix_semantics.py`
- **Log**: `/workspace/logs/tests/posix_semantics.log`
- **Summary**: Advanced POSIX semantics (O_CREAT|O_EXCL, lseek, fsync, truncate extend/shrink, chmod, rename, ENOTEMPTY, ENOENT) all correct.

### 2.3 concurrency_test (new) — ✅ passed
- **Suite**: correctness
- **Command**: `MOUNTPOINT=/mnt/agentfs python3 concurrency_test.py`
- **Log**: `/workspace/logs/tests/concurrency_test.log`
- **Summary**: 8 threads each doing 100 iterations of create/write/read/verify/unlink — no data corruption detected. Elapsed: 0.34s.

### 2.4 edge_case_test (new) — ✅ passed
- **Suite**: correctness
- **Command**: `MOUNTPOINT=/mnt/agentfs python3 edge_case_test.py`
- **Log**: `/workspace/logs/tests/edge_case_test.log`
- **Summary**: Cross-block writes (4097 bytes), sparse file via truncate (64KB), zero-length files, rename-over-existing, deep nested directories, ENOENT on rmdir, EEXIST on mkdir, chmod mode bits, fsync, truncate-to-zero, O_EXCL, large filenames (200 chars), truncate-extend zero-fill. All passed.

### 2.5 symlink_test (new) — ❌ failed
- **Suite**: correctness
- **Command**: `MOUNTPOINT=/mnt/agentfs python3 symlink_test.py`
- **Log**: `/workspace/logs/tests/symlink_test.log`
- **Summary**: `os.symlink()` returns `OSError: [Errno 38] Function not implemented`. Symlink support is declared in `requirement_result.json` (features.symlink=true, operations include symlink/readlink) but the running filesystem does not implement the `symlink` FUSE callback.

### 2.6 xattr_test (new) — ❌ failed
- **Suite**: correctness
- **Command**: `MOUNTPOINT=/mnt/agentfs python3 xattr_test.py`
- **Log**: `/workspace/logs/tests/xattr_test.log`
- **Summary**: `os.setxattr()` returns `OSError: [Errno 95] Operation not supported`. Extended attribute support is declared in `requirement_result.json` (features.xattrs=true, operations include setxattr/getxattr/listxattr/removexattr) but the running filesystem does not implement these callbacks.

---

## 3. Stress Tests

### 3.1 stress_metadata (template) — ✅ passed
- **Suite**: stress
- **Command**: `MOUNTPOINT=/mnt/agentfs STRESS_DURATION_SEC=10 STRESS_WORKERS=4 python3 stress_metadata.py`
- **Log**: `/workspace/logs/tests/stress_metadata.log`
- **Summary**: 4 processes performing concurrent create/write/read/rename/unlink/rmdir loops for 10 seconds. No failures. All worker exit codes 0.

---

## 4. Benchmark Tests

### 4.1 fs_mark_quick (template) — ✅ passed
- **Suite**: benchmark
- **Command**: `MOUNTPOINT=/mnt/agentfs FSMARK_FILES=500 FSMARK_THREADS=4 bash fs_mark_quick.sh`
- **Log**: `/workspace/logs/tests/fs_mark_quick.log`
- **Metrics**:
  - Files created+deleted: 500
  - Threads: 4
  - Elapsed: 0.135s
  - **Files/sec**: 3693.43

### 4.2 fio_quick (template) — ✅ passed
- **Suite**: benchmark
- **Command**: `fio fio_quick.fio` (sync engine, 4K block, 10s per job)
- **Log**: `/workspace/logs/tests/fio_quick.log`
- **Metrics**:

| Job      | Operation | IOPS       | Bandwidth (KiB/s) |
|----------|-----------|------------|-------------------|
| seqwrite | write     | 17,245.9   | 68,983.0          |
| seqread  | read      | 18,237.5   | 72,949.0          |
| randrw   | read      | 8,814.7    | 35,258.0          |
| randrw   | write     | 3,807.6    | 15,230.0          |

---

## 5. Issues Summary

| # | Type | Severity | Summary | Log |
|---|------|----------|---------|-----|
| 1 | `correctness` | High | **symlink not implemented**: `os.symlink()` returns ENOSYS (Errno 38). Declared in requirement_result.json but missing from running FS. | `/workspace/logs/tests/symlink_test.log` |
| 2 | `correctness` | High | **xattr not implemented**: `os.setxattr()` returns EOPNOTSUPP (Errno 95). Declared in requirement_result.json but missing from running FS. | `/workspace/logs/tests/xattr_test.log` |

---

## 6. Overall Assessment

- **Core POSIX operations**: All working correctly (create, read, write, truncate, rename, chmod, mkdir, rmdir, unlink, fsync)
- **Concurrency**: No data corruption under parallel load
- **Edge cases**: Cross-block I/O, sparse files, deep paths, O_EXCL — all correct
- **Declared-but-missing features**: symlink and xattr — the `requirement_result.json` declares these features but the actual generated filesystem binary (`fs_ir.json`) does NOT include them (fs_ir.json features.symlink=false, features.xattrs=false, and operations list lacks symlink/readlink/setxattr/getxattr/listxattr/removexattr). **The requirement_result.json over-declares capabilities not present in the actual build.**

**Test Status**: **FAILED** — 2 correctness failures (symlink, xattr) due to feature declaration mismatch. Core functionality is sound.
