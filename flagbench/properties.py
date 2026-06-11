"""
Four formal correctness properties for runtime feature flag resolvers.

Each function accepts a resolver callable and a ResolutionInput,
and returns (passed: bool, detail: str).

Properties:
  1. Determinism          — same input always → same output
  2. Fallback safety      — no eligible version → fallback_version returned
  3. Compliance precedence — approved version always beats pending/deprecated
  4. Monotonic rollout    — higher rollout_pct → higher or equal selection rate
"""
from __future__ import annotations
from copy import deepcopy
from typing import Callable

from flagbench.schema import (
    ComplianceStatus, ResolutionInput, ResolutionOutput,
)

Resolver = Callable[[ResolutionInput], ResolutionOutput]


def check_determinism(
    resolver: Resolver,
    inp: ResolutionInput,
    n_calls: int = 5,
) -> tuple[bool, str]:
    """Property 1: identical input must produce identical output across all calls."""
    outputs = [resolver(inp) for _ in range(n_calls)]
    first = outputs[0]
    for i, o in enumerate(outputs[1:], 1):
        if o.version_id != first.version_id or o.is_fallback != first.is_fallback:
            return False, (
                f"Non-determinism on call {i + 1}: "
                f"got version={o.version_id!r} is_fallback={o.is_fallback}, "
                f"expected version={first.version_id!r} is_fallback={first.is_fallback}"
            )
    return True, "ok"


def check_fallback_safety(
    resolver: Resolver,
    inp: ResolutionInput,
) -> tuple[bool, str]:
    """
    Property 2: when all rollout_pcts are 0 (no version is eligible),
    the resolver must return the declared fallback_version with is_fallback=True.
    """
    forced = deepcopy(inp)
    for v in forced.config.version_set:
        v.rollout_pct = 0.0

    out = resolver(forced)

    if not out.is_fallback:
        return False, (
            f"Expected is_fallback=True when all rollout_pcts=0, "
            f"got version={out.version_id!r} is_fallback={out.is_fallback}"
        )
    if out.version_id != forced.config.fallback_version.version_id:
        return False, (
            f"Wrong fallback version: "
            f"expected {forced.config.fallback_version.version_id!r}, "
            f"got {out.version_id!r}"
        )
    return True, "ok"


def check_compliance_precedence(
    resolver: Resolver,
    inp: ResolutionInput,
) -> tuple[bool, str]:
    """
    Property 3: if any approved version has rollout_pct=1.0,
    the resolver must not select a pending or deprecated version.
    """
    forced = deepcopy(inp)
    has_approved = False
    for v in forced.config.version_set:
        if v.compliance_status == ComplianceStatus.APPROVED:
            v.rollout_pct = 1.0
            has_approved = True

    if not has_approved:
        return True, "skip — no approved version in set"

    out = resolver(forced)

    if out.is_fallback:
        # Acceptable only if the fallback itself is approved
        fb_status = forced.config.fallback_version.compliance_status
        if fb_status != ComplianceStatus.APPROVED:
            return False, (
                f"Fallback selected but fallback version is {fb_status.value}, "
                f"not approved — compliance precedence violated"
            )
        return True, "ok (fallback selected; fallback is approved)"

    if out.compliance_status != ComplianceStatus.APPROVED:
        return False, (
            f"Compliance precedence violated: selected {out.version_id!r} "
            f"with status={out.compliance_status.value!r} "
            f"when an approved version with rollout_pct=1.0 was eligible"
        )
    return True, "ok"


def check_monotonic_rollout(
    resolver: Resolver,
    inp: ResolutionInput,
    target_version_id: str,
    delta: float = 0.2,
    n_seeds: int = 200,
    tolerance: float = 0.05,
) -> tuple[bool, str]:
    """
    Property 4: increasing rollout_pct of a target version must not
    decrease its selection frequency across a synthetic user population.

    Statistical test: tolerance of ±5% accounts for sampling noise.
    """
    from flagbench.schema import UserContext, UserTier

    # Locate the target version's current rollout
    current_rollout: float | None = None
    for v in inp.config.version_set:
        if v.version_id == target_version_id:
            current_rollout = v.rollout_pct
            break

    if current_rollout is None:
        return True, f"skip — {target_version_id!r} not found in version_set"

    def selection_rate(rollout: float) -> float:
        chosen = 0
        for i in range(n_seeds):
            test_inp = deepcopy(inp)
            test_inp.user = UserContext(
                user_id=f"synthetic_user_{i:04d}",
                tier=UserTier.STANDARD,
                region="US",
                compliance_group="A",
            )
            for v in test_inp.config.version_set:
                if v.version_id == target_version_id:
                    v.rollout_pct = rollout
            out = resolver(test_inp)
            if out.version_id == target_version_id:
                chosen += 1
        return chosen / n_seeds

    low_rate = selection_rate(current_rollout)
    high_rollout = min(1.0, current_rollout + delta)
    high_rate = selection_rate(high_rollout)

    if high_rate < low_rate - tolerance:
        return False, (
            f"Monotonicity violated for {target_version_id!r}: "
            f"rollout {current_rollout:.0%} → {high_rollout:.0%} "
            f"but selection rate {low_rate:.2%} → {high_rate:.2%} (decreased by "
            f"{low_rate - high_rate:.2%}, tolerance={tolerance:.0%})"
        )
    return True, (
        f"ok — rollout {current_rollout:.0%} → {high_rollout:.0%}, "
        f"rate {low_rate:.2%} → {high_rate:.2%}"
    )
