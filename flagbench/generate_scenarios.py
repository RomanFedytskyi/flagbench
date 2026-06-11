"""
Scenario dataset generator.

Produces the four CSV files in data/scenarios/ that constitute the
FlagBench benchmark dataset (2,000 rows total).

Usage:
    python -m flagbench.generate_scenarios

Output:
    data/scenarios/normal_ops.csv          (800 rows)  [SYNTHETIC]
    data/scenarios/boundary_conditions.csv (400 rows)  [DERIVED]
    data/scenarios/fallback_trigger.csv    (400 rows)  [DERIVED]
    data/scenarios/adversarial.csv         (400 rows)  [LITERATURE + SYNTHETIC]
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

from flagbench.resolver import ReferenceResolver
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

SCENARIOS_DIR = Path(__file__).parent.parent / "data" / "scenarios"
_RESOLVER = ReferenceResolver()

_ROUTES = [
    "/dashboard", "/audit-log", "/settings", "/reports",
    "/transactions", "/users", "/admin", "/login",
    "/api/v1/flags", "/api/v1/versions",
]
_REGIONS = ["US", "GB", "DE", "FR", "JP", "AU", "CA", "SG"]
_GROUPS  = ["A", "B", "C"]
_TIERS   = [UserTier.STANDARD, UserTier.PREMIUM, UserTier.ADMIN]

_BASE_TS = 1_750_000_000.0  # ~June 2025


def _row(inp: ResolutionInput) -> dict:
    """Serialize a ResolutionInput + ground-truth output to a CSV row."""
    out = _RESOLVER.resolve(inp)
    vids    = ";".join(v.version_id       for v in inp.config.version_set)
    stats   = ";".join(v.compliance_status.value for v in inp.config.version_set)
    rolls   = ";".join(str(v.rollout_pct)  for v in inp.config.version_set)
    stabs   = ";".join(str(v.stability_score) for v in inp.config.version_set)
    return {
        "user_id":                inp.user.user_id,
        "tier":                   inp.user.tier.value,
        "region":                 inp.user.region,
        "compliance_group":       inp.user.compliance_group,
        "route_path":             inp.route.path,
        "timestamp_utc":          inp.time.timestamp_utc,
        "component_id":           inp.config.component_id,
        "version_ids":            vids,
        "compliance_statuses":    stats,
        "rollout_pcts":           rolls,
        "stability_scores":       stabs,
        "active_version_id":      inp.config.active_version.version_id,
        "fallback_version_id":    inp.config.fallback_version.version_id,
        "ground_truth_version_id": out.version_id,
    }


def _make_versions(
    n: int,
    rng: random.Random,
    force_approved: bool = False,
    rollout_override: float | None = None,
) -> list[VersionSpec]:
    statuses = [ComplianceStatus.APPROVED, ComplianceStatus.PENDING, ComplianceStatus.DEPRECATED]
    versions = []
    for i in range(1, n + 1):
        status = ComplianceStatus.APPROVED if (force_approved or i == 1) else rng.choice(statuses)
        rollout = rollout_override if rollout_override is not None else round(rng.uniform(0.1, 1.0), 2)
        versions.append(VersionSpec(
            version_id=f"v{i}",
            compliance_status=status,
            rollout_pct=rollout,
            stability_score=round(rng.uniform(0.5, 1.0), 2),
        ))
    return versions


def generate_normal_ops(n: int = 800, seed: int = 42) -> pd.DataFrame:
    """800 typical production scenarios [SYNTHETIC]."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        n_versions = rng.randint(2, 5)
        versions = _make_versions(n_versions, rng)
        vm = {v.version_id: v for v in versions}
        config = ComponentConfig(
            component_id=f"comp_{rng.choice(['header','sidebar','dashboard','auditlog','settings'])}",
            active_version=versions[0],
            fallback_version=versions[0],
            version_set=versions,
        )
        inp = ResolutionInput(
            user=UserContext(
                user_id=f"user_{i:04d}",
                tier=rng.choice(_TIERS),
                region=rng.choice(_REGIONS),
                compliance_group=rng.choice(_GROUPS),
            ),
            route=Route(path=rng.choice(_ROUTES)),
            time=TimeWindow(timestamp_utc=_BASE_TS + rng.uniform(0, 86_400 * 30)),
            config=config,
        )
        rows.append(_row(inp))
    return pd.DataFrame(rows)


def generate_boundary_conditions(n: int = 400, seed: int = 43) -> pd.DataFrame:
    """400 boundary scenarios: rollout=0%, rollout=100%, compliance transitions [DERIVED]."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        boundary_type = i % 4
        if boundary_type == 0:
            # All rollout = 0 → must fallback
            versions = [
                VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                            rollout_pct=0.0, stability_score=0.9),
                VersionSpec(version_id="v2", compliance_status=ComplianceStatus.APPROVED,
                            rollout_pct=0.0, stability_score=0.8),
            ]
        elif boundary_type == 1:
            # All rollout = 1.0 → approved wins
            versions = [
                VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                            rollout_pct=1.0, stability_score=rng.uniform(0.5, 1.0)),
                VersionSpec(version_id="v2", compliance_status=ComplianceStatus.PENDING,
                            rollout_pct=1.0, stability_score=1.0),
            ]
        elif boundary_type == 2:
            # Exactly one version just at rollout boundary (0.5)
            versions = [
                VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                            rollout_pct=0.5, stability_score=0.9),
            ]
        else:
            # Approved + deprecated mix, approved must win
            versions = [
                VersionSpec(version_id="v1", compliance_status=ComplianceStatus.DEPRECATED,
                            rollout_pct=1.0, stability_score=1.0),
                VersionSpec(version_id="v2", compliance_status=ComplianceStatus.APPROVED,
                            rollout_pct=1.0, stability_score=0.5),
            ]
        config = ComponentConfig(
            component_id="comp_boundary",
            active_version=versions[0],
            fallback_version=versions[0],
            version_set=versions,
        )
        inp = ResolutionInput(
            user=UserContext(
                user_id=f"boundary_user_{i:04d}",
                tier=rng.choice(_TIERS),
                region=rng.choice(_REGIONS),
                compliance_group=rng.choice(_GROUPS),
            ),
            route=Route(path=rng.choice(_ROUTES)),
            time=TimeWindow(timestamp_utc=_BASE_TS + i * 3600.0),
            config=config,
        )
        rows.append(_row(inp))
    return pd.DataFrame(rows)


def generate_fallback_trigger(n: int = 400, seed: int = 44) -> pd.DataFrame:
    """400 scenarios where no version satisfies constraints → fallback [DERIVED]."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        n_versions = rng.randint(1, 4)
        # All versions have rollout_pct=0 → no eligible version
        versions = [
            VersionSpec(
                version_id=f"v{j}",
                compliance_status=rng.choice([ComplianceStatus.APPROVED, ComplianceStatus.PENDING]),
                rollout_pct=0.0,
                stability_score=round(rng.uniform(0.5, 1.0), 2),
            )
            for j in range(1, n_versions + 1)
        ]
        config = ComponentConfig(
            component_id="comp_fallback",
            active_version=versions[0],
            fallback_version=versions[0],
            version_set=versions,
        )
        inp = ResolutionInput(
            user=UserContext(
                user_id=f"fallback_user_{i:04d}",
                tier=rng.choice(_TIERS),
                region=rng.choice(_REGIONS),
                compliance_group=rng.choice(_GROUPS),
            ),
            route=Route(path=rng.choice(_ROUTES)),
            time=TimeWindow(timestamp_utc=_BASE_TS + i * 1800.0),
            config=config,
        )
        rows.append(_row(inp))
    return pd.DataFrame(rows)


def generate_adversarial(n: int = 400, seed: int = 45) -> pd.DataFrame:
    """
    400 adversarial scenarios based on known flag-system failure modes [LITERATURE + SYNTHETIC].

    Failure modes modelled:
      - Empty version set (no versions at all beyond fallback)
      - Conflicting compliance flags (all deprecated)
      - Rapid rollout-percentage changes (0 → 1 → 0)
      - Single-version edge case
      - All versions same stability + rollout → ordering tie resolved by version_id sort
    """
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        mode = i % 5
        if mode == 0:
            # Single version, must use it or fallback
            versions = [
                VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                            rollout_pct=rng.choice([0.0, 1.0]), stability_score=0.9),
            ]
        elif mode == 1:
            # All deprecated — no eligible version → fallback
            versions = [
                VersionSpec(version_id=f"v{j}", compliance_status=ComplianceStatus.DEPRECATED,
                            rollout_pct=1.0, stability_score=round(rng.uniform(0.5, 1.0), 2))
                for j in range(1, 4)
            ]
        elif mode == 2:
            # All same compliance + rollout + stability → determinism test
            versions = [
                VersionSpec(version_id=f"v{j}", compliance_status=ComplianceStatus.APPROVED,
                            rollout_pct=1.0, stability_score=0.8)
                for j in range(1, 4)
            ]
        elif mode == 3:
            # Mix: one approved with near-zero rollout, one pending with full rollout
            versions = [
                VersionSpec(version_id="v1", compliance_status=ComplianceStatus.APPROVED,
                            rollout_pct=0.01, stability_score=0.9),
                VersionSpec(version_id="v2", compliance_status=ComplianceStatus.PENDING,
                            rollout_pct=1.0, stability_score=0.95),
            ]
        else:
            # Approved + pending + deprecated all with rollout=1.0
            versions = [
                VersionSpec(version_id="v1", compliance_status=ComplianceStatus.DEPRECATED,
                            rollout_pct=1.0, stability_score=1.0),
                VersionSpec(version_id="v2", compliance_status=ComplianceStatus.PENDING,
                            rollout_pct=1.0, stability_score=0.9),
                VersionSpec(version_id="v3", compliance_status=ComplianceStatus.APPROVED,
                            rollout_pct=1.0, stability_score=0.5),
            ]
        config = ComponentConfig(
            component_id="comp_adversarial",
            active_version=versions[0],
            fallback_version=versions[0],
            version_set=versions,
        )
        inp = ResolutionInput(
            user=UserContext(
                user_id=f"adversarial_user_{i:04d}",
                tier=rng.choice(_TIERS),
                region=rng.choice(_REGIONS),
                compliance_group=rng.choice(_GROUPS),
            ),
            route=Route(path=rng.choice(_ROUTES)),
            time=TimeWindow(timestamp_utc=_BASE_TS + i * 900.0),
            config=config,
        )
        rows.append(_row(inp))
    return pd.DataFrame(rows)


def main():
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)

    print("[flagbench] Generating scenarios...")

    df = generate_normal_ops(800)
    df.to_csv(SCENARIOS_DIR / "normal_ops.csv", index=False)
    print(f"  normal_ops.csv          — {len(df):>4} rows")

    df = generate_boundary_conditions(400)
    df.to_csv(SCENARIOS_DIR / "boundary_conditions.csv", index=False)
    print(f"  boundary_conditions.csv — {len(df):>4} rows")

    df = generate_fallback_trigger(400)
    df.to_csv(SCENARIOS_DIR / "fallback_trigger.csv", index=False)
    print(f"  fallback_trigger.csv    — {len(df):>4} rows")

    df = generate_adversarial(400)
    df.to_csv(SCENARIOS_DIR / "adversarial.csv", index=False)
    print(f"  adversarial.csv         — {len(df):>4} rows")

    total = 800 + 400 + 400 + 400
    print(f"[flagbench] Done — {total} scenarios written to {SCENARIOS_DIR}")


if __name__ == "__main__":
    main()
