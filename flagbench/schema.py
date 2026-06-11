"""
Canonical data models for FlagBench.
All other modules import from here — never duplicate these types.

Formal model reference:
  Fedytskyi, R. (2025). Dynamic Frontend Architecture for Runtime Component
  Versioning and Feature Flag Resolution in Regulated Applications.
  Software, 4(4), 32. https://doi.org/10.3390/software4040032
"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ComplianceStatus(str, Enum):
    APPROVED = "approved"
    PENDING = "pending"
    DEPRECATED = "deprecated"


class UserTier(str, Enum):
    STANDARD = "standard"
    PREMIUM = "premium"
    ADMIN = "admin"


class UserContext(BaseModel):
    user_id: str
    tier: UserTier
    region: str                         # ISO-3166 alpha-2, e.g. "US"
    compliance_group: str               # e.g. "A", "B", "C"
    extra: dict = Field(default_factory=dict)


class Route(BaseModel):
    path: str                           # e.g. "/dashboard", "/audit-log"


class TimeWindow(BaseModel):
    timestamp_utc: float                # Unix timestamp


class VersionSpec(BaseModel):
    version_id: str                     # e.g. "v1", "v2", "v3"
    compliance_status: ComplianceStatus
    rollout_pct: float = Field(ge=0.0, le=1.0)   # 0.0 = 0%, 1.0 = 100%
    stability_score: float = Field(ge=0.0, le=1.0)


class ComponentConfig(BaseModel):
    component_id: str
    active_version: VersionSpec
    fallback_version: VersionSpec
    version_set: list[VersionSpec]      # all deployable versions


class ResolutionInput(BaseModel):
    user: UserContext
    route: Route
    time: TimeWindow
    config: ComponentConfig


class ResolutionOutput(BaseModel):
    version_id: str
    is_fallback: bool
    compliance_status: ComplianceStatus
    resolution_time_ms: Optional[float] = None
