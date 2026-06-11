"""
Metric computation functions. Pure — no side effects, no I/O.

Used by the benchmark harness to produce standardised scores
that can be compared across resolver implementations.
"""
from __future__ import annotations
import statistics
from flagbench.schema import ComplianceStatus, ResolutionOutput


def resolution_accuracy(
    outputs: list[ResolutionOutput],
    ground_truth: list[str],
) -> float:
    """Fraction of outputs where version_id matches ground truth."""
    if not outputs:
        return 0.0
    correct = sum(
        1 for o, g in zip(outputs, ground_truth) if o.version_id == g
    )
    return correct / len(outputs)


def fallback_rate(outputs: list[ResolutionOutput]) -> float:
    """Fraction of outputs where is_fallback=True."""
    if not outputs:
        return 0.0
    return sum(1 for o in outputs if o.is_fallback) / len(outputs)


def latency_percentiles(
    outputs: list[ResolutionOutput],
) -> dict[str, float]:
    """
    P50, P90, P99, and mean resolution latency in milliseconds.
    Returns an empty dict if no timing data is present.
    """
    times = [
        o.resolution_time_ms
        for o in outputs
        if o.resolution_time_ms is not None
    ]
    if not times:
        return {}
    times_sorted = sorted(times)
    n = len(times_sorted)
    return {
        "p50":  round(times_sorted[max(0, int(n * 0.50) - 1)], 4),
        "p90":  round(times_sorted[max(0, int(n * 0.90) - 1)], 4),
        "p99":  round(times_sorted[max(0, int(n * 0.99) - 1)], 4),
        "mean": round(statistics.mean(times), 4),
    }


def compliance_violation_count(outputs: list[ResolutionOutput]) -> int:
    """
    Count non-fallback outputs where a non-approved version was selected.
    Used as a compliance health indicator: higher = worse.
    """
    return sum(
        1 for o in outputs
        if not o.is_fallback
        and o.compliance_status != ComplianceStatus.APPROVED
    )
