"""
Reference resolver: implements v = f(u, r, t) as formalized in
Fedytskyi (2025), DOI 10.3390/software4040032.

Ordering ≻ on VersionSpec (three-level hierarchy):
  1. compliance_status: approved > pending > deprecated
  2. rollout_pct (descending)
  3. stability_score (descending)

This is the ground truth against which all adapters are compared.
Thread-safe (stateless).
"""
from __future__ import annotations
import time
from flagbench.schema import (
    ComplianceStatus, ComponentConfig,
    ResolutionInput, ResolutionOutput, VersionSpec,
)

_COMPLIANCE_RANK: dict[ComplianceStatus, int] = {
    ComplianceStatus.APPROVED: 2,
    ComplianceStatus.PENDING: 1,
    ComplianceStatus.DEPRECATED: 0,
}


def _dominates(a: VersionSpec, b: VersionSpec) -> bool:
    """Return True if a ≻ b (a is strictly preferred over b)."""
    ra = _COMPLIANCE_RANK[a.compliance_status]
    rb = _COMPLIANCE_RANK[b.compliance_status]
    if ra != rb:
        return ra > rb
    if a.rollout_pct != b.rollout_pct:
        return a.rollout_pct > b.rollout_pct
    return a.stability_score > b.stability_score


def _compliance_eligible(v: VersionSpec) -> bool:
    return v.compliance_status != ComplianceStatus.DEPRECATED


def _rollout_eligible(v: VersionSpec, user_seed: int) -> bool:
    """Deterministic: user is 'in' rollout if their bucket < rollout_pct."""
    bucket = (user_seed % 10_000) / 10_000.0
    return bucket < v.rollout_pct


def _derive_seed(inp: ResolutionInput) -> int:
    """Deterministic seed from (user_id, route.path, UTC day)."""
    day = int(inp.time.timestamp_utc // 86_400)
    raw = f"{inp.user.user_id}::{inp.route.path}::{day}"
    return hash(raw) & 0x7FFF_FFFF


def _select_version(
    config: ComponentConfig, user_seed: int
) -> tuple[VersionSpec, bool]:
    """
    Select the highest-ranked eligible version.
    Returns (selected_version, is_fallback).
    """
    eligible = [
        v for v in config.version_set
        if _compliance_eligible(v) and _rollout_eligible(v, user_seed)
    ]
    if not eligible:
        return config.fallback_version, True

    best = eligible[0]
    for v in eligible[1:]:
        if _dominates(v, best):
            best = v
    return best, False


class ReferenceResolver:
    """Reference implementation of v = f(u, r, t)."""

    def resolve(self, inp: ResolutionInput) -> ResolutionOutput:
        t0 = time.perf_counter()
        seed = _derive_seed(inp)
        version, is_fallback = _select_version(inp.config, seed)
        elapsed_ms = (time.perf_counter() - t0) * 1_000
        return ResolutionOutput(
            version_id=version.version_id,
            is_fallback=is_fallback,
            compliance_status=version.compliance_status,
            resolution_time_ms=round(elapsed_ms, 4),
        )
