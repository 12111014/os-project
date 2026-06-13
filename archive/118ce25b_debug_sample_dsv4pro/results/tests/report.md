# agentfs FUSE Filesystem Test Report

## Summary

| Item              | Result                |
|-------------------|-----------------------|
| **Overall Status**| **PASSED**            |
| Filesystem        | agentfs (libfuse3, in-memory) |
| Mountpoint        | /mnt/agentfs         |
| Test Timestamp    | 2026-06-11           |

## Suites Run

1. `preflight` — mount and basic health checks
2. `posix_smoke` — basic POSIX operations smoke test
3. `posix_semantics` — detailed POSIX semantics validation
4. `feature_discrepancy` — symlink and xattr capability verification (found in runtime vs fs_ir)
5. `extended_correctness` — comprehensive correctness suite (17 tests)
6. `stress_metadata` — concurrent metadata operations under load
7. `fs_mark_quick` — quick metadata throughput benchmark

## Test Results

### 1. Preflight Mount Checks

| Case                  | Status  | Summary |
|-----------------------|---------|---------|
| mountpoint_exists     | passed  | /mnt/agentfs exists as directory |
| mountpoint_writable   | passed  | create/write/read/delete works |
| df_reports_size       | passed  | 1.0G total, 0 used |
| stat_root             | passed  | Inode 1, dir, mode 0755, uid=0, gid=0 |

### 2. POSIX Smoke Test (`posix_smoke.sh`)

| Case                  | Status  | Summary |
|-----------------------|---------|---------|
| file_create_write     | passed  | echo hello → file |
| file_read             | passed  | content matches |
| mkdir                 | passed  | directory created |
| nested_file           | passed  | file in subdirectory |
| rename (mv)           | passed  | file moved across directories |
| truncate              | passed  | truncate -s 2 reduces content |
| chmod                 | passed  | permissions changed to 600 |
| unlink                | passed  | file removal works |
| rmdir                 | passed  | empty directory removed |
| cleanup_verification  | passed  | no leftovers |

- **Log**: `/workspace/logs/tests/posix_smoke.log`

### 3. POSIX Semantics Test (`posix_semantics.py`)

| Case                  | Status  | Summary |
|-----------------------|---------|---------|
| create_excl           | passed  | O_CREAT | O_EXCL |
| write_read_seek       | passed  | seek to offset, partial read |
| fsync                 | passed  | fsync before close |
| truncate_shrink       | passed  | truncate to 3 → content "abc" |
| truncate_grow         | passed  | grow back to 6, size=6 |
| chmod                 | passed  | 0o600 verified |
| rename                | passed  | file renamed, old path gone |
| rmdir_nonempty        | passed  | ENOTEMPTY correctly raised |
| readdir               | passed  | sorted entries verified |
| unlink_rmdir_sequence | passed  | child removed, then dir |
| enoent_on_missing     | passed  | ENOENT for missing file |

- **Log**: `/workspace/logs/tests/posix_semantics.log`

### 4. Feature Discrepancy Check

The `fs_ir.json` claims `"symlink": false` and `"xattrs": false`, but the runtime filesystem **actually supports** both symlinks and extended attributes. This was confirmed via Python os.* calls.

| Case                  | Status  | Summary |
|-----------------------|---------|---------|
| symlink_create        | passed  | os.symlink() succeeds |
| symlink_readlink      | passed  | os.readlink() returns correct target |
| xattr_set             | passed  | os.setxattr() succeeds |
| xattr_get             | passed  | os.getxattr() returns correct value |
| xattr_list            | passed  | os.listxattr() lists attributes |
| xattr_remove          | passed  | os.removexattr() succeeds |

- **Log**: `/workspace/logs/tests/feature_discrepancy.log`

> **Note**: The `requirement_result.json` (confidence 0.95) correctly predicted `symlink: true` and `xattrs: true`. The `fs_ir.json` likely reflects an older/incorrect baseline. The `architecture.json` lists only 13 operations without symlink/xattr, so the generated filesystem has more features than the architecture specified.

### 5. Extended Correctness Tests (`extended_correctness.py`)

17 comprehensive tests, all passed:

| # | Case                          | Status  |
|---|-------------------------------|---------|
| 1 | symlink_create_and_readlink   | passed  |
| 2 | symlink_dangling              | passed  |
| 3 | symlink_rename                | passed  |
| 4 | symlink_unlink_keeps_target   | passed  |
| 5 | xattr_basic                   | passed  |
| 6 | xattr_multiple                | passed  |
| 7 | xattr_on_dir                  | passed  |
| 8 | large_write_read (128KB)      | passed  |
| 9 | sparse_truncate (→1MB)        | passed  |
| 10 | many_files_in_dir (200)       | passed  |
| 11 | deep_directories (50 levels)  | passed  |
| 12 | rename_across_dirs            | passed  |
| 13 | fsync                         | passed  |
| 14 | chmod_on_dir                  | passed  |
| 15 | empty_file                    | passed  |
| 16 | rmdir_nonempty                | passed  |
| 17 | recreate_after_unlink         | passed  |

- **Log**: `/workspace/logs/tests/extended_correctness.log`

### 6. Stress Test (`stress_metadata.py`)

| Case                  | Status  | Summary |
|-----------------------|---------|---------|
| concurrent_metadata   | passed  | 4 workers × 15s, continuous create/write/read/rename/unlink/rmdir loops |

- **Log**: `/workspace/logs/tests/stress_metadata.log`

### 7. Quick Benchmark (`fs_mark_quick.sh`)

| Metric                | Value               |
|-----------------------|---------------------|
| Files created+deleted | 1000                |
| Threads               | 4                   |
| File size             | 4096 bytes          |
| Elapsed time          | 0.382 s             |
| Throughput            | ~2620 files/sec     |

- **Log**: `/workspace/logs/tests/fs_mark_quick.log`

## Issues

No failures or regressions found. One minor observation:

| Type    | Summary | Details |
|---------|---------|---------|
| info    | fs_ir.json underreports features | fs_ir claims symlink=false, xattrs=false; runtime supports both |

## Conclusion

The agentfs FUSE filesystem is **fully functional**. All correctness tests (smoke, semantics, extended, and stress) pass. Symlink and xattr features work despite being marked as unsupported in `fs_ir.json`. Metadata throughput is ~2620 files/sec on simple create/delete workloads. No correctness bugs, crashes, or data corruption observed.
