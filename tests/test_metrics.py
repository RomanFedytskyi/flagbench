"""Unit tests for all metric functions."""
from flagbench.schema import ComplianceStatus, ResolutionOutput
from flagbench.metrics import (
    compliance_violation_count,
    fallback_rate,
    latency_percentiles,
    resolution_accuracy,
)


def _out(vid, is_fallback=False, status=ComplianceStatus.APPROVED, ms=1.0):
    return ResolutionOutput(
        version_id=vid, is_fallback=is_fallback,
        compliance_status=status, resolution_time_ms=ms,
    )


def test_accuracy_perfect():
    outputs = [_out("v1"), _out("v2"), _out("v1")]
    assert resolution_accuracy(outputs, ["v1", "v2", "v1"]) == 1.0


def test_accuracy_partial():
    outputs = [_out("v1"), _out("v2")]
    assert resolution_accuracy(outputs, ["v1", "v1"]) == 0.5


def test_accuracy_empty():
    assert resolution_accuracy([], []) == 0.0


def test_fallback_rate_all_fallback():
    outputs = [_out("v1", is_fallback=True)] * 4
    assert fallback_rate(outputs) == 1.0


def test_fallback_rate_mixed():
    outputs = [_out("v1", is_fallback=True), _out("v2"), _out("v1", is_fallback=True)]
    assert abs(fallback_rate(outputs) - 2 / 3) < 1e-9


def test_fallback_rate_empty():
    assert fallback_rate([]) == 0.0


def test_latency_percentiles_100_items():
    outputs = [_out("v1", ms=float(i)) for i in range(1, 101)]
    p = latency_percentiles(outputs)
    assert p["p50"] == 50.0
    assert p["p90"] == 90.0
    assert p["p99"] == 99.0


def test_latency_percentiles_empty():
    outputs = [_out("v1", ms=None)]
    assert latency_percentiles(outputs) == {}


def test_compliance_violations_counts_non_approved_non_fallback():
    outputs = [
        _out("v1", status=ComplianceStatus.APPROVED),
        _out("v2", status=ComplianceStatus.PENDING),
        _out("v3", status=ComplianceStatus.DEPRECATED),
        _out("v4", is_fallback=True, status=ComplianceStatus.PENDING),  # not counted
    ]
    assert compliance_violation_count(outputs) == 2


def test_compliance_violations_zero_when_all_approved():
    outputs = [_out(f"v{i}", status=ComplianceStatus.APPROVED) for i in range(5)]
    assert compliance_violation_count(outputs) == 0
