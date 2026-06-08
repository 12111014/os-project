from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class MountAttempt(BaseModel):
    command: str = Field(description="The mount command attempted by the agent.")
    exit_code: int | None = Field(
        default=None,
        description="Exit code of the command if available.",
    )
    observation: str = Field(
        default="",
        description="Short observation from command output, logs, or mount check.",
    )


class MountIssue(BaseModel):
    type: str
    summary: str


class MountAgentResult(BaseModel):
    mount_status: Literal["mounted", "failed"] = Field(
        description="Whether the FUSE filesystem was mounted successfully."
    )

    mount_command: str = Field(
        default="",
        description="Final command used to mount the filesystem.",
    )

    mountpoint: str = Field(
        default="/mnt/agentfs",
        description="FUSE mountpoint inside the sandbox.",
    )

    pid_path: str = Field(
        default="/workspace/run/fuse.pid",
        description="Path of the file storing the FUSE daemon PID.",
    )

    log_path: str = Field(
        default="/workspace/logs/fuse.log",
        description="Path of the FUSE stdout/stderr log.",
    )

    filesystem_type: str | None = Field(
        default=None,
        description="Filesystem type reported by mount/findmnt, e.g. fuse.agentfs.",
    )

    diagnosis: str = Field(
        default="",
        description="Human-readable diagnosis of the mount result.",
    )

    attempts: list[MountAttempt] = Field(
        default_factory=list,
        description="Mount attempts made by the agent.",
    )

    issues: list[MountIssue] = Field(
        default_factory=list,
        description="Non-fatal or fatal issues discovered during mounting.",
    )