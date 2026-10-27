"""Schemas for public installer download analytics."""

from datetime import datetime

from pydantic import BaseModel, Field


class InstallerVersionStat(BaseModel):
    """Aggregated download count for a requested installer version."""

    version: str
    count: int


class InstallerDownloadStats(BaseModel):
    """Summary statistics for installer script downloads."""

    audit_enabled: bool
    days: int
    total_downloads: int
    downloads_last_24h: int
    unique_ips: int
    cli_downloads: int
    oss_downloads: int
    pinned_downloads: int
    latest_version_downloads: int
    last_download_at: datetime | None = None
    top_versions: list[InstallerVersionStat] = Field(default_factory=list)
