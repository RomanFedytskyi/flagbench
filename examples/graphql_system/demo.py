"""
End-to-end demo: run FlagBench against the example GraphQL flag server.

Prerequisites:
    # Terminal 1 — start the flag server
    pip install flask
    FLAGSERVER_TOKEN=dev-token python examples/graphql_system/server.py

    # Terminal 2 — run this demo
    pip install -r requirements.txt requests
    GRAPHQL_URL=http://localhost:4000/graphql \
    GRAPHQL_TOKEN=dev-token \
    python examples/graphql_system/demo.py

What this demo does:
    1. Resolves each of your real flag names directly (smoke test)
    2. Runs the full FlagBench benchmark harness against the GraphQL adapter
    3. Runs the property-based oracle (Hypothesis)
    4. Prints an annotated summary with what each result means for your app
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time

# Make sure flagbench package is importable when running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.dirname(__file__))

from flagbench.schema import (
    ComplianceStatus, ComponentConfig, ResolutionInput,
    Route, TimeWindow, UserContext, UserTier, VersionSpec,
)

# ---------------------------------------------------------------------------
# Require credentials before doing anything
# ---------------------------------------------------------------------------
def _check_env() -> None:
    missing = [v for v in ("GRAPHQL_URL", "GRAPHQL_TOKEN") if not os.environ.get(v)]
    if missing:
        print("\n[error] Missing required environment variables:", ", ".join(missing))
        print("  Set them before running:")
        print("    export GRAPHQL_URL=http://localhost:4000/graphql")
        print("    export GRAPHQL_TOKEN=dev-token")
        sys.exit(1)

_check_env()

# Import after env check so adapter can validate config at import time
import adapter as graphql_adapter   # noqa: E402

# ---------------------------------------------------------------------------
# Step 1 — Smoke test: resolve your real flags directly
# ---------------------------------------------------------------------------
def smoke_test() -> None:
    print("\n" + "="*60)
    print("STEP 1 — Smoke test: resolve your real flags")
    print("="*60)

    # Each tuple: (flag_name, known_versions, fallback_version_id)
    YOUR_FLAGS = [
        ("creEnabled",       ["enabled", "disabled"], "disabled"),
        ("helocEnabled",     ["enabled", "disabled"], "disabled"),
        ("loanWriteMode",    ["v1", "hybrid", "v2"],  "v1"),
        ("asyncPoolCreation",["enabled", "disabled"], "disabled"),
        ("remittanceEnabled",["enabled", "disabled"], "disabled"),
        ("bidsTableVersion", ["v1", "v2"],            "v1"),
        ("poolFiltersVersion",["v1", "v2"],           "v1"),
    ]

    for flag_name, versions, fallback_id in YOUR_FLAGS:
        version_set = [
            VersionSpec(
                version_id=v,
                compliance_status=ComplianceStatus.APPROVED,
                rollout_pct=1.0,
                stability_score=1.0,
            )
            for v in versions
        ]
        fallback = next(v for v in version_set if v.version_id == fallback_id)

        inp = ResolutionInput(
            user=UserContext(user_id="demo-user-001", tier=UserTier.STANDARD,
                             region="US", compliance_group="A"),
            route=Route(path="/dashboard"),
            time=TimeWindow(timestamp_utc=time.time()),
            config=ComponentConfig(
                component_id=flag_name,
                active_version=version_set[0],
                fallback_version=fallback,
                version_set=version_set,
            ),
        )

        result = graphql_adapter.resolve(inp)
        status = "FALLBACK" if result.is_fallback else "ACTIVE"
        print(f"  {flag_name:<25} → {result.version_id:<12} [{status}]  "
              f"{result.resolution_time_ms:.2f} ms")

    print("\n  ✓ Smoke test complete — adapter is calling your flag service correctly.")


# ---------------------------------------------------------------------------
# Step 2 — FlagBench harness
# ---------------------------------------------------------------------------
def run_harness() -> None:
    print("\n" + "="*60)
    print("STEP 2 — FlagBench benchmark harness (2,000 scenarios)")
    print("="*60)
    print("  Running... (this calls your GraphQL endpoint once per scenario)\n")

    from flagbench.harness import run_benchmark
    summary = run_benchmark(graphql_adapter.resolve, "graphql_system")

    if not summary:
        print("  [warn] No scenarios found. Run generate_scenarios.py first.")
        return

    overall = summary.get("overall", {})
    print(f"  Accuracy:              {overall.get('accuracy', 0):.1%}")
    print(f"  Compliance violations: {overall.get('compliance_violations', 0)}")
    lat = overall.get("latency_ms", {})
    print(f"  Latency p50/p90/p99:   "
          f"{lat.get('p50',0)*1000:.1f} μs / "
          f"{lat.get('p90',0)*1000:.1f} μs / "
          f"{lat.get('p99',0)*1000:.1f} μs")

    print("\n  What this means for your financial app:")
    accuracy = overall.get('accuracy', 0)
    violations = overall.get('compliance_violations', 0)

    if accuracy >= 0.95:
        print("  ✓ Accuracy ≥ 95% — resolver is behaving correctly across all scenario types.")
    elif accuracy >= 0.80:
        print("  ⚠ Accuracy 80–95% — investigate boundary_conditions and adversarial groups.")
    else:
        print("  ✗ Accuracy < 80% — significant correctness gap. Review flag resolution logic.")

    if violations == 0:
        print("  ✓ Zero compliance violations — approved versions always selected when eligible.")
    else:
        print(f"  ✗ {violations} compliance violations — a non-approved version was selected "
              f"when an approved one was available. This is an audit risk in regulated contexts.")


# ---------------------------------------------------------------------------
# Step 3 — Property verification
# ---------------------------------------------------------------------------
def run_properties() -> None:
    print("\n" + "="*60)
    print("STEP 3 — Property verification (Hypothesis oracle)")
    print("="*60)
    print("  Run this separately for full output:")
    print("  pytest flagbench/oracle.py -v --hypothesis-seed=0\n")

    try:
        from flagbench.properties import (
            check_determinism, check_fallback_safety, check_compliance_precedence,
        )
        from flagbench.schema import ComponentConfig, VersionSpec, ComplianceStatus

        vs = [
            VersionSpec(version_id="enabled",  compliance_status=ComplianceStatus.APPROVED, rollout_pct=1.0, stability_score=1.0),
            VersionSpec(version_id="disabled", compliance_status=ComplianceStatus.DEPRECATED, rollout_pct=0.0, stability_score=0.0),
        ]
        fb = vs[1]
        sample_inp = ResolutionInput(
            user=UserContext(user_id="prop-test-user", tier=UserTier.STANDARD,
                             region="US", compliance_group="A"),
            route=Route(path="/test"),
            time=TimeWindow(timestamp_utc=time.time()),
            config=ComponentConfig(
                component_id="creEnabled",
                active_version=vs[0],
                fallback_version=fb,
                version_set=vs,
            ),
        )

        for name, check_fn in [
            ("P1 Determinism",     check_determinism),
            ("P2 Fallback Safety", check_fallback_safety),
        ]:
            passed, detail = check_fn(graphql_adapter.resolve, sample_inp)
            mark = "✓" if passed else "✗"
            print(f"  {mark} {name}: {'PASS' if passed else 'FAIL'} — {detail}")

        print("\n  P3 Compliance Precedence and P4 Monotonic Rollout require your backend")
        print("  to expose complianceStatus and rolloutPct in the GraphQL response.")
        print("  See adapter.py: GRAPHQL_QUERY_EXTENDED for the extended query.")
    except Exception as exc:
        print(f"  [warn] Could not run inline property checks: {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\nFlagBench × GraphQL System — End-to-End Demo")
    print(f"Target: {os.environ['GRAPHQL_URL']}")
    smoke_test()
    run_harness()
    run_properties()
    print("\n" + "="*60)
    print("Demo complete.")
    print("Results written to: results/summary_graphql_system.json")
    print("="*60)
