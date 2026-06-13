from typing import Literal
from pydantic import BaseModel, Field


FuseOperation = Literal[
    "getattr",
    "readdir",
    "mkdir",
    "rmdir",
    "create",
    "open",
    "read",
    "write",
    "unlink",
    "rename",
    "truncate",
    "chmod",
    "chown",
    "utimens",
    "fsync",
    "flush",
    "release",
    "symlink",
    "readlink",
    "link",
    "statfs",
]


class StorageSpec(BaseModel):
    # type: Literal["memory", "image_file", "passthrough"] = "memory"
    type: str = "memory"
    # block_size: int = 4096
    # image_size_mb: int = 1024


class FeatureSpec(BaseModel):
    directories: bool = True
    symlink: bool = False
    hardlink: bool = False
    permissions: Literal["none", "basic"] = "basic"
    journaling: bool = False
    xattrs: bool = False


class ValidationSpec(BaseModel):
    posix_smoke: bool = True
    pytest: bool = True
    fio: bool = False
    fsmark: bool = False
    xfstests: bool = False


class FilesystemIR(BaseModel):
    name: str = "agentfs"
    target: Literal["fuse"] = "fuse"
    language: Literal["c", "cpp", "rust", "python"] = "c"
    backend: Literal["libfuse3"] = "libfuse3"
    storage: StorageSpec = Field(default_factory=StorageSpec)
    features: FeatureSpec = Field(default_factory=FeatureSpec)
    operations: list[FuseOperation] = Field(default_factory=list)
    validation: ValidationSpec = Field(default_factory=ValidationSpec)
    extra_field: list[str] = Field(default_factory=list, description="Extra specifications does not in IR schema")