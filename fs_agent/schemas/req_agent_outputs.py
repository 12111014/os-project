from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class StorageSpec(BaseModel):
    type: str = Field(
        default="memory",
        description="Storage backend type: memory, image_file, or passthrough"
    )
    block_size: int = Field(default=4096, description="Block size in bytes")
    image_size_mb: int = Field(default=1024, description="Image size in MB for image_file storage")


class FeatureSpec(BaseModel):
    directories: bool = Field(default=True, description="Support directories")
    symlink: bool = Field(default=False, description="Support symbolic links")
    hardlink: bool = Field(default=False, description="Support hard links")
    permissions: Literal["none", "basic"] = Field(default="basic", description="Permission model")
    journaling: bool = Field(default=False, description="Enable journaling")
    xattrs: bool = Field(default=False, description="Support extended attributes")


class ValidationSpec(BaseModel):
    posix_smoke: bool = Field(default=True, description="Run POSIX smoke tests")
    pytest: bool = Field(default=True, description="Run pytest suite")
    fio: bool = Field(default=False, description="Run fio benchmarks")
    filebench: bool = Field(default=False, description="Run filebench benchmarks")
    xfstests: bool = Field(default=False, description="Run xfstests suite")


class RequirementParserResult(BaseModel):
    success: bool = Field(description="Whether parsing succeeded")

    name: str = Field(
        default="agentfs",
        description="Filesystem name"
    )

    target: Literal["fuse"] = Field(
        default="fuse",
        description="Target framework"
    )

    language: Literal["c", "rust", "python"] = Field(
        default="c",
        description="Implementation language"
    )

    backend: Literal["libfuse3"] = Field(
        default="libfuse3",
        description="Backend library"
    )

    storage: StorageSpec = Field(
        default_factory=StorageSpec,
        description="Storage backend specification"
    )

    features: FeatureSpec = Field(
        default_factory=FeatureSpec,
        description="Feature flags"
    )

    operations: list[str] = Field(
        default_factory=list,
        description="List of FUSE operations to implement"
    )

    validation: ValidationSpec = Field(
        default_factory=ValidationSpec,
        description="Validation and testing configuration"
    )

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score of the parsing result"
    )

    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about ambiguous or conflicting requirements"
    )

    reasoning: str = Field(
        default="",
        description="Explanation of design decisions"
    )