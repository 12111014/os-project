#!/usr/bin/env python3
"""Extended correctness tests covering symlinks, xattrs, and edge cases for agentfs."""

import errno
import os
import shutil
import stat
import sys
from pathlib import Path


def require_errno(fn, expected: int) -> None:
    try:
        fn()
    except OSError as exc:
        if exc.errno == expected:
            return
        raise AssertionError(f"expected errno {expected}, got {exc.errno}") from exc
    raise AssertionError(f"expected errno {expected}, got success")


def test_symlink_create_and_readlink(root: Path) -> None:
    target = root / "sym_target"
    target.write_text("target content")
    link = root / "sym_link"
    os.symlink(str(target), str(link))
    assert os.path.islink(str(link))
    assert os.readlink(str(link)) == str(target)
    assert link.read_text() == "target content"
    target.unlink()
    link.unlink()
    print("  symlink_create_and_readlink: passed")


def test_symlink_dangling(root: Path) -> None:
    link = root / "dangling"
    os.symlink("/nonexistent/path", str(link))
    assert os.path.islink(str(link))
    assert os.readlink(str(link)) == "/nonexistent/path"
    require_errno(lambda: link.read_text(), errno.ENOENT)
    link.unlink()
    print("  symlink_dangling: passed")


def test_symlink_rename(root: Path) -> None:
    target = root / "sym_rename_target"
    target.write_text("hello")
    link = root / "sym_rename_link"
    os.symlink(str(target), str(link))
    newlink = root / "sym_renamed"
    os.rename(str(link), str(newlink))
    assert not link.exists()
    assert os.path.islink(str(newlink))
    assert newlink.read_text() == "hello"
    target.unlink()
    newlink.unlink()
    print("  symlink_rename: passed")


def test_symlink_unlink(root: Path) -> None:
    target = root / "sym_unlink_target"
    target.write_text("data")
    link = root / "sym_unlink_link"
    os.symlink(str(target), str(link))
    link.unlink()
    assert not link.exists()
    assert target.exists()
    assert target.read_text() == "data"
    target.unlink()
    print("  symlink_unlink_keeps_target: passed")


def test_xattr_basic(root: Path) -> None:
    f = root / "xattr_file"
    f.write_text("data")
    os.setxattr(str(f), "user.meta", b"myvalue")
    assert os.getxattr(str(f), "user.meta") == b"myvalue"
    attrs = os.listxattr(str(f))
    assert "user.meta" in attrs
    os.removexattr(str(f), "user.meta")
    require_errno(lambda: os.getxattr(str(f), "user.meta"), errno.ENODATA)
    f.unlink()
    print("  xattr_basic: passed")


def test_xattr_multiple(root: Path) -> None:
    f = root / "xattr_multi"
    f.write_text("data")
    os.setxattr(str(f), "user.a", b"1")
    os.setxattr(str(f), "user.b", b"2")
    os.setxattr(str(f), "user.c", b"3")
    attrs = os.listxattr(str(f))
    for a in ["user.a", "user.b", "user.c"]:
        assert a in attrs, f"missing {a} in {attrs}"
    assert os.getxattr(str(f), "user.a") == b"1"
    assert os.getxattr(str(f), "user.b") == b"2"
    assert os.getxattr(str(f), "user.c") == b"3"
    os.removexattr(str(f), "user.a")
    require_errno(lambda: os.getxattr(str(f), "user.a"), errno.ENODATA)
    assert os.getxattr(str(f), "user.b") == b"2"
    f.unlink()
    print("  xattr_multiple: passed")


def test_xattr_on_dir(root: Path) -> None:
    d = root / "xattr_dir"
    d.mkdir()
    os.setxattr(str(d), "user.dirattr", b"dirvalue")
    assert os.getxattr(str(d), "user.dirattr") == b"dirvalue"
    attrs = os.listxattr(str(d))
    assert "user.dirattr" in attrs
    os.removexattr(str(d), "user.dirattr")
    d.rmdir()
    print("  xattr_on_dir: passed")


def test_large_write_read(root: Path) -> None:
    f = root / "large_file"
    data = b"A" * 65536 + b"B" * 65536  # 128KB
    f.write_bytes(data)
    assert f.stat().st_size == 131072
    assert f.read_bytes() == data
    f.unlink()
    print("  large_write_read: passed")


def test_sparse_truncate(root: Path) -> None:
    f = root / "sparse_file"
    f.write_text("hello")
    os.truncate(str(f), 1048576)  # 1MB - zero-fill
    st = f.stat()
    assert st.st_size == 1048576, f"size={st.st_size}"
    content = f.read_bytes()
    assert content[0:5] == b"hello"
    assert content[5:10] == b"\x00" * 5
    f.unlink()
    print("  sparse_truncate: passed")


def test_many_files_in_dir(root: Path) -> None:
    d = root / "many_files_dir"
    d.mkdir()
    count = 200
    for i in range(count):
        (d / f"file_{i:04d}").write_text(f"content_{i}")
    entries = list(d.iterdir())
    assert len(entries) == count, f"expected {count}, got {len(entries)}"
    for i in range(count):
        (d / f"file_{i:04d}").unlink()
    d.rmdir()
    print("  many_files_in_dir: passed")


def test_deep_directories(root: Path) -> None:
    current = root / "deep"
    current.mkdir()
    for i in range(50):
        current = current / f"level_{i}"
        current.mkdir()
    leaf = current / "leaf.txt"
    leaf.write_text("deep data")
    assert leaf.read_text() == "deep data"
    shutil.rmtree(str(root / "deep"))
    print("  deep_directories: passed")


def test_rename_across_dirs(root: Path) -> None:
    d1 = root / "ren_src"
    d1.mkdir()
    d2 = root / "ren_dst"
    d2.mkdir()
    f = d1 / "file.txt"
    f.write_text("move me")
    dest = d2 / "moved.txt"
    os.rename(str(f), str(dest))
    assert not f.exists()
    assert dest.exists()
    assert dest.read_text() == "move me"
    dest.unlink()
    d1.rmdir()
    d2.rmdir()
    print("  rename_across_dirs: passed")


def test_fsync_and_fdatasync(root: Path) -> None:
    f = root / "fsync_test"
    fd = os.open(str(f), os.O_CREAT | os.O_RDWR, 0o644)
    os.write(fd, b"fsync data")
    os.fsync(fd)
    os.close(fd)
    assert f.read_bytes() == b"fsync data"
    f.unlink()
    print("  fsync: passed")


def test_chmod_on_dir(root: Path) -> None:
    d = root / "chmod_dir"
    d.mkdir(mode=0o755)
    os.chmod(str(d), 0o700)
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    d.rmdir()
    print("  chmod_on_dir: passed")


def test_empty_file(root: Path) -> None:
    f = root / "empty"
    f.touch()
    assert f.stat().st_size == 0
    assert f.read_bytes() == b""
    f.unlink()
    print("  empty_file: passed")


def test_rmdir_nonempty_consistent(root: Path) -> None:
    d = root / "nonempty_dir"
    d.mkdir()
    child = d / "child.txt"
    child.write_text("data")
    require_errno(lambda: d.rmdir(), errno.ENOTEMPTY)
    child.unlink()
    d.rmdir()
    print("  rmdir_nonempty: passed")


def test_recreate_file_after_unlink(root: Path) -> None:
    f = root / "recreate"
    f.write_text("v1")
    f.unlink()
    f.write_text("v2")
    assert f.read_text() == "v2"
    f.unlink()
    print("  recreate_after_unlink: passed")


def main() -> int:
    mountpoint = Path(os.environ.get("MOUNTPOINT", "/mnt/agentfs"))
    root = mountpoint / f".agentfs-extended-{os.getpid()}"
    if root.exists():
        shutil.rmtree(str(root))
    root.mkdir()
    failed = 0
    try:
        tests = [
            test_symlink_create_and_readlink,
            test_symlink_dangling,
            test_symlink_rename,
            test_symlink_unlink,
            test_xattr_basic,
            test_xattr_multiple,
            test_xattr_on_dir,
            test_large_write_read,
            test_sparse_truncate,
            test_many_files_in_dir,
            test_deep_directories,
            test_rename_across_dirs,
            test_fsync_and_fdatasync,
            test_chmod_on_dir,
            test_empty_file,
            test_rmdir_nonempty_consistent,
            test_recreate_file_after_unlink,
        ]
        for t in tests:
            try:
                t(root)
            except Exception as e:
                print(f"  FAIL: {t.__name__}: {e}")
                failed += 1
    finally:
        shutil.rmtree(str(root), ignore_errors=True)

    if failed:
        print(f"extended_correctness: FAILED ({failed}/{len(tests)} failures)")
        return 1
    print("extended_correctness: passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
