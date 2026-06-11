"""
Tests that each property function correctly classifies
known-good and known-bad resolvers.
"""
import pytest
from flagbench.schema import (
    ComplianceStatus, ComponentConfig, ResolutionInput, ResolutionOutput,
    Route, TimeWindow, UserContext, UserTier, VersionSpec,
)
from flagbench import (
    check_determinism, check_fallback_safety, check_compliance_precedence,
)
from flagbench.resolver import ReferenceResolver


def _base_input() -> ResolutionInput:
    versions = [
        VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                    rollout_pct=1.0, stability_score=0.9),
        VersionSpec(version_id="v2", compliance_status=ComplianceStatus.PENDING,
                    rollout_pct=1.0, stability_score=0.7),
    ]
    config = ComponentConfig(
        component_id="c1",
        active_version=versions[0],
        fallback_version=versions[0],
        version_set=versions,
    )
    return ResolutionInput(
        user=UserContext(user_id="u1", tier=UserTier.STANDARD, region="US", compliance_group="A"),
        route=Route(path="/dashboard"),
        time=TimeWindow(timestamp_utc=1_750_000_000.0),
        config=config,
    )


# --- Determinism ---

def test_determinism_passes_reference():
    resolver = ReferenceResolver()
    passed, _ = check_determinism(resolver.resolve, _base_input())
    assert passed


def test_determinism_fails_nondeterministic_resolver():
    counter = [0]
    def bad_resolver(inp):
        counter[0] += 1
        vid = "v1" if counter[0] % 2 == 0 else "v2"
        return ResolutionOutput(
            version_id=vid, is_fallback=False,
            compliance_status=ComplianceStatus.APPROVED,
        )
    passed, detail = check_determinism(bad_resolver, _base_input())
    assert not passed
    assert "Non-determinism" in detail


# --- Fallback safety ---

def test_fallback_safety_passes_reference():
    resolver = ReferenceResolver()
    passed, _ = check_fallback_safety(resolver.resolve, _base_input())
    assert passed


def test_fallback_safety_fails_resolver_ignoring_rollout():
    def bad_resolver(inp):
        # Always returns v2, even when rollout=0
        return ResolutionOutput(
            version_id="v2", is_fallback=False,
            compliance_status=ComplianceStatus.PENDING,
        )
    passed, detail = check_fallback_safety(bad_resolver, _base_input())
    assert not passed
    assert "is_fallback=True" in detail


# --- Compliance precedence ---

def test_compliance_precedence_passes_reference():
    resolver = ReferenceResolver()
    passed, _ = check_compliance_precedence(resolver.resolve, _base_input())
    assert passed


def test_compliance_precedence_fails_when_pending_selected():
    def bad_resolver(inp):
        # Always selects v2 (pending) even when v1 (approved) is eligible
        return ResolutionOutput(
            version_id="v2", is_fallback=False,
            compliance_status=ComplianceStatus.PENDING,
        )
    passed, detail = check_compliance_precedence(bad_resolver, _base_input())
    assert not passed
    assert "Compliance precedence violated" in detail


def test_compliance_precedence_skips_when_no_approved():
    versions = [
        VersionSpec(version_id="v1", compliance_status=ComplianceStatus.PENDING,
                    rollout_pct=1.0, stability_score=0.9),
    ]
    config = _base_input().config.model_copy(update={"version_set": versions,
                                                      "active_version": versions[0],
                                                      "fallback_version": versions[0]})
    inp = _base_input().model_copy(update={"config": config})
    resolver = ReferenceResolver()
    passed, detail = check_compliance_precedence(resolver.resolve, inp)
    assert passed
    assert "skip" in detail
