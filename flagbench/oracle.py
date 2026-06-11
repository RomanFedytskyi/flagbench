"""
Property-based oracle using Hypothesis.

Generates arbitrary ResolutionInput instances and verifies each of the
four correctness properties against the reference resolver.

Run via pytest:
    pytest flagbench/oracle.py -v
    pytest flagbench/oracle.py -v --hypothesis-seed=0   # fixed seed for CI
"""
from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from flagbench.schema import (
    ComplianceStatus,
    ComponentConfig,
    ResolutionInput,
    Route,
    TimeWindow,
    UserContext,
    UserTier,
    VersionSpec,
)
from flagbench.resolver import ReferenceResolver
from flagbench import (
    check_compliance_precedence,
    check_determinism,
    check_fallback_safety,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_compliance_st = st.sampled_from(list(ComplianceStatus))
_tier_st = st.sampled_from(list(UserTier))
_region_st = st.sampled_from(["US", "GB", "DE", "FR", "JP", "AU", "CA", "SG"])
_group_st = st.sampled_from(["A", "B", "C"])
_routes = [
    "/dashboard", "/audit-log", "/settings", "/reports",
    "/transactions", "/users", "/admin", "/login",
    "/api/v1/flags", "/api/v1/versions",
]

user_context_st = st.builds(
    UserContext,
    user_id=st.text(min_size=1, max_size=16, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))),
    tier=_tier_st,
    region=_region_st,
    compliance_group=_group_st,
)

route_st = st.builds(Route, path=st.sampled_from(_routes))

time_window_st = st.builds(
    TimeWindow,
    timestamp_utc=st.floats(
        min_value=1_700_000_000.0,
        max_value=1_800_000_000.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)

version_spec_st = st.builds(
    VersionSpec,
    version_id=st.from_regex(r"v[1-9][0-9]?", fullmatch=True),
    compliance_status=_compliance_st,
    rollout_pct=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    stability_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)


@st.composite
def component_config_st(draw: st.DrawFn) -> ComponentConfig:
    versions = draw(st.lists(version_spec_st, min_size=1, max_size=8))
    active = draw(st.sampled_from(versions))
    fallback = draw(st.sampled_from(versions))
    return ComponentConfig(
        component_id=draw(st.from_regex(r"comp_[a-z]{1,4}", fullmatch=True)),
        active_version=active,
        fallback_version=fallback,
        version_set=versions,
    )


resolution_input_st = st.builds(
    ResolutionInput,
    user=user_context_st,
    route=route_st,
    time=time_window_st,
    config=component_config_st(),
)

# ---------------------------------------------------------------------------
# Oracle — one test per property
# ---------------------------------------------------------------------------

_resolver = ReferenceResolver()
_SETTINGS = settings(
    max_examples=1_000,
    suppress_health_check=[HealthCheck.too_slow],
)


@given(inp=resolution_input_st)
@_SETTINGS
def test_oracle_determinism(inp: ResolutionInput) -> None:
    """Property 1: identical input → identical output."""
    passed, detail = check_determinism(_resolver.resolve, inp)
    assert passed, f"DETERMINISM VIOLATED\n{detail}\nInput:\n{inp.model_dump_json(indent=2)}"


@given(inp=resolution_input_st)
@_SETTINGS
def test_oracle_fallback_safety(inp: ResolutionInput) -> None:
    """Property 2: all-zero rollout → declared fallback returned."""
    passed, detail = check_fallback_safety(_resolver.resolve, inp)
    assert passed, f"FALLBACK SAFETY VIOLATED\n{detail}\nInput:\n{inp.model_dump_json(indent=2)}"


@given(inp=resolution_input_st)
@_SETTINGS
def test_oracle_compliance_precedence(inp: ResolutionInput) -> None:
    """Property 3: approved version always beats pending/deprecated."""
    passed, detail = check_compliance_precedence(_resolver.resolve, inp)
    assert passed, f"COMPLIANCE PRECEDENCE VIOLATED\n{detail}\nInput:\n{inp.model_dump_json(indent=2)}"
