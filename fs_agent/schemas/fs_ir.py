from typing import Literal
from pydantic import BaseModel, Field


class StorageSpec(BaseModel):
    # type: Literal["memory", "image_file", "passthrough"] = "memory"
    type: str = "memory"
    block_size: int = 4096
    image_size_mb: int = 1024


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
    filebench: bool = False
    xfstests: bool = False


class FilesystemIR(BaseModel):
    name: str = "agentfs"
    target: Literal["fuse"] = "fuse"
    language: Literal["c", "rust", "python"] = "c"
    backend: Literal["libfuse3"] = "libfuse3"
    storage: StorageSpec = Field(default_factory=StorageSpec)
    features: FeatureSpec = Field(default_factory=FeatureSpec)
    operations: list[str] = Field(
        default_factory=lambda: [
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
            "fsync",
        ]
    )
    validation: ValidationSpec = Field(default_factory=ValidationSpec)