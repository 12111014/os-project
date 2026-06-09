from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

class ModuleSpec(BaseModel):
    name: str = Field(description="Module name")
    responsibility: str = Field(description="Module responsibility")
    files: list[str] = Field(default_factory=list, description="Source files in this module")


class DataStructureSpec(BaseModel):
    name: str = Field(description="Data structure name")
    description: str = Field(description="Purpose and design")
    fields: list[str] = Field(default_factory=list, description="Key fields")


class ArchitecturePlanResult(BaseModel):
    success: bool = Field(description="Whether architecture design succeeded")

    modules: list[ModuleSpec] = Field(
        default_factory=list,
        description="Module decomposition"
    )

    data_model: dict[str, str] = Field(
        default_factory=dict,
        description="Data model description (name -> description)"
    )

    data_structures: list[DataStructureSpec] = Field(
        default_factory=list,
        description="Key data structures"
    )

    fuse_operations: list[str] = Field(
        default_factory=list,
        description="FUSE operations to implement"
    )

    api_boundaries: list[str] = Field(
        default_factory=list,
        description="Module API boundaries"
    )

    limitations: list[str] = Field(
        default_factory=list,
        description="Known limitations and out-of-scope features"
    )

    threading_model: str = Field(
        default="mutex-based",
        description="Concurrency control strategy"
    )

    memory_management: str = Field(
        default="dynamic allocation with cleanup",
        description="Memory management strategy"
    )

    error_handling: str = Field(
        default="errno-based",
        description="Error handling pattern"
    )

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score of the architecture design"
    )

    reasoning: str = Field(
        default="",
        description="Explanation of architectural decisions"
    )

    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about potential issues"
    )
