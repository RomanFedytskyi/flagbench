"""
Simulated Unleash adapter — models realistic correctness gaps
that emerge when a generic flag system is used in a compliance-aware context.

Three deliberate gaps (documented in the paper):

  GAP 1 — Compliance precedence ignored:
    Unleash evaluates toggles purely by rollout percentage and variant weight.
    It has no concept of compliance_status ordering. A PENDING version with
    rollout_pct=1.0 can beat an APPROVED version with rollout_pct=0.5.
    This violates Property 3 (compliance_precedence).

  GAP 2 — Non-deterministic rollout bucketing:
    The real Unleash SDK uses MurmurHash3 over (toggleName + userId) for
    bucketing. Our simulated adapter uses Python's built-in hash(), which
    is randomised across interpreter restarts (PYTHONHASHSEED).
    This violates Property 1 (determinism) in cross-process scenarios.

  GAP 3 — Wrong fallback on empty eligibility:
    When no variant is enabled, Unleash returns the 'disabled' variant
    (an implicit default), not the application's declared fallback_version.
    This violates Property 2 (fallback_safety).
"""
from __future__ import annotations

import random
from flagbench.schema import (
    ComplianceStatus, ResolutionInput, ResolutionOutput,
)

# Fixed seed for reproducibility in benchmarking — in production the real
# Unleash SDK does NOT fix this seed, making it non-deterministic across restarts.
_RNG = random.Random(99)


def _unleash_bucket(user_id: str, component_id: str) -> float:
    """
    Simulates Unleash's variant bucketing — uses non-cryptographic hash
    that varies by PYTHONHASHSEED in real deployments.
    Fixed here for reproducible benchmarking; in production this would
    differ across interpreter restarts.
    """
    raw = hash(f"{component_id}:{user_id}") & 0x7FFF_FFFF
    return (raw % 10_000) / 10_000.0


def resolve(inp: ResolutionInput) -> ResolutionOutput:
    """
    Simulated Unleash resolution with three known correctness gaps.
    """
    versions = inp.config.version_set

    # GAP 1: No compliance ordering — sort only by rollout_pct descending.
    # Approved vs pending vs deprecated are treated identically.
    # Deprecated versions are NOT filtered out (Unleash has no concept of it).
    eligible = [
        v for v in versions
        if _unleash_bucket(inp.user.user_id, inp.config.component_id) < v.rollout_pct
    ]

    if not eligible:
        # GAP 3: Return first version in set rather than declared fallback.
        # This mimics Unleash returning its 'disabled' variant (index 0 of
        # variant definitions) rather than the app-declared fallback.
        wrong_fallback = versions[0] if versions else inp.config.fallback_version
        return ResolutionOutput(
            version_id=wrong_fallback.version_id,
            is_fallback=True,  # is_fallback=True is correct here
            compliance_status=wrong_fallback.compliance_status,
        )

    # GAP 1 continued: pick highest rollout_pct regardless of compliance status.
    best = max(eligible, key=lambda v: (v.rollout_pct, v.stability_score))

    return ResolutionOutput(
        version_id=best.version_id,
        is_fallback=False,
        compliance_status=best.compliance_status,
    )
