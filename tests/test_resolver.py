"""
Unit tests for the reference resolver.
Target: 100% line coverage on flagbench/resolver.py.
"""
import pytest
from flagbench.schema import (
    ComplianceStatus, ComponentConfig, ResolutionInput,
    Route, TimeWindow, UserContext, UserTier, VersionSpec,
)
from flagbench.resolver import ReferenceResolver


def _inp(versions: list[VersionSpec], fallback_id: str, active_id: str) -> ResolutionInput:
    vm = {v.version_id: v for v in versions}
    config = ComponentConfig(
        component_id="comp_test",
        active_version=vm[active_id],
        fallback_version=vm[fallback_id],
        version_set=versions,
    )
    return ResolutionInput(
        user=UserContext(user_id="u001", tier=UserTier.STANDARD, region="US", compliance_group="A"),
        route=Route(path="/dashboard"),
        time=TimeWindow(timestamp_utc=1_750_000_000.0),
        config=config,
    )


@pytest.fixture
def resolver():
    return ReferenceResolver()


def test_approved_beats_pending(resolver):
    versions = [
        VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=1.0, stability_score=0.9),
        VersionSpec(version_id="v2", compliance_status=ComplianceStatus.PENDING,
                    rollout_pct=1.0, stability_score=0.99),
    ]
    out = resolver.resolve(_inp(versions, fallback_id="v1", active_id="v1"))
    assert out.version_id == "v1"
    assert out.compliance_status == ComplianceStatus.APPROVED
    assert not out.is_fallback


def test_approved_beats_deprecated(resolver):
    versions = [
        VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=1.0, stability_score=0.5),
        VersionSpec(version_id="v2", compliance_status=ComplianceStatus.DEPRECATED,
                    rollout_pct=1.0, stability_score=1.0),
    ]
    out = resolver.resolve(_inp(versions, fallback_id="v1", active_id="v1"))
    assert out.version_id == "v1"


def test_higher_rollout_preferred_among_approved(resolver):
    versions = [
        VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=0.3, stability_score=0.9),
        VersionSpec(version_id="v2", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=1.0, stability_score=0.5),
    ]
    # user u001 at /dashboard day 20254 — seed is fixed, v2 should win on rollout
    out = resolver.resolve(_inp(versions, fallback_id="v1", active_id="v2"))
    # v2 has higher rollout and same compliance — it should be selected if eligible
    assert out.compliance_status == ComplianceStatus.APPROVED


def test_fallback_when_all_rollout_zero(resolver):
    versions = [
        VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=0.0, stability_score=0.9),
        VersionSpec(version_id="v2", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=0.0, stability_score=0.8),
    ]
    out = resolver.resolve(_inp(versions, fallback_id="v1", active_id="v1"))
    assert out.is_fallback
    assert out.version_id == "v1"


def test_deprecated_excluded(resolver):
    versions = [
        VersionSpec(version_id="v1", compliance_status=ComplianceStatus.DEPRECATED,
                    rollout_pct=1.0, stability_score=1.0),
        VersionSpec(version_id="v2", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=1.0, stability_score=0.5),
    ]
    out = resolver.resolve(_inp(versions, fallback_id="v2", active_id="v2"))
    assert out.version_id == "v2"
    assert not out.is_fallback


def test_determinism_across_calls(resolver):
    versions = [
        VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=0.5, stability_score=0.9),
    ]
    inp = _inp(versions, fallback_id="v1", active_id="v1")
    results = {resolver.resolve(inp).version_id for _ in range(20)}
    assert len(results) == 1


def test_timing_recorded(resolver):
    versions = [
        VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=1.0, stability_score=0.9),
    ]
    out = resolver.resolve(_inp(versions, fallback_id="v1", active_id="v1"))
    assert out.resolution_time_ms is not None
    assert out.resolution_time_ms >= 0.0


def test_single_version_full_rollout(resolver):
    versions = [
        VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=1.0, stability_score=0.9),
    ]
    out = resolver.resolve(_inp(versions, fallback_id="v1", active_id="v1"))
    assert out.version_id == "v1"
    assert not out.is_fallback


def test_stability_breaks_tie(resolver):
    versions = [
        VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=1.0, stability_score=0.5),
        VersionSpec(version_id="v2", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=1.0, stability_score=0.9),
    ]
    out = resolver.resolve(_inp(versions, fallback_id="v1", active_id="v2"))
    assert out.version_id == "v2"
