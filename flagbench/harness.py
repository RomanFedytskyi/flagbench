"""
Benchmark runner.

Loads scenario CSVs from data/scenarios/, runs them through any resolver
implementing the ResolutionAdapter protocol, and writes results/summary_<adapter>.json.

Usage:
    python -m flagbench.harness --adapter reference
    python -m flagbench.harness --adapter unleash
"""
from __future__ import annotations

import argparse
import importlib
import json
import time
from pathlib import Path
from typing import Callable

import pandas as pd

from flagbench.metrics import (
    compliance_violation_count,
    fallback_rate,
    latency_percentiles,
    resolution_accuracy,
)
from flagbench.schema import (
    ComplianceStatus,
    ComponentConfig,
    ResolutionInput,
    ResolutionOutput,
    Route,
    TimeWindow,
    UserContext,
    UserTier,
    VersionSpec,
)

SCENARIOS_DIR = Path(__file__).parent.parent / "data" / "scenarios"
RESULTS_DIR   = Path(__file__).parent.parent / "results"

Resolver = Callable[[ResolutionInput], ResolutionOutput]


def _load_scenarios(csv_path: Path) -> tuple[list[ResolutionInput], list[str]]:
    """
    Parse a scenario CSV into (inputs, ground_truth_version_ids).

    Expected columns:
      user_id, tier, region, compliance_group,
      route_path, timestamp_utc,
      component_id,
      version_ids          (semicolon-separated, e.g. "v1;v2;v3")
      compliance_statuses  (semicolon-separated, e.g. "approved;pending;deprecated")
      rollout_pcts         (semicolon-separated floats)
      stability_scores     (semicolon-separated floats)
      active_version_id, fallback_version_id,
      ground_truth_version_id
    """
    df = pd.read_csv(csv_path)
    inputs: list[ResolutionInput] = []
    truths: list[str] = []

    for _, row in df.iterrows():
        version_ids   = str(row["version_ids"]).split(";")
        statuses      = str(row["compliance_statuses"]).split(";")
        rollouts      = [float(x) for x in str(row["rollout_pcts"]).split(";")]
        stabilities   = [float(x) for x in str(row["stability_scores"]).split(";")]

        versions = [
            VersionSpec(
                version_id=vid,
                compliance_status=ComplianceStatus(s),
                rollout_pct=r,
                stability_score=st_,
            )
            for vid, s, r, st_ in zip(version_ids, statuses, rollouts, stabilities)
        ]
        vm = {v.version_id: v for v in versions}

        config = ComponentConfig(
            component_id=str(row["component_id"]),
            active_version=vm[str(row["active_version_id"])],
            fallback_version=vm[str(row["fallback_version_id"])],
            version_set=versions,
        )
        inp = ResolutionInput(
            user=UserContext(
                user_id=str(row["user_id"]),
                tier=UserTier(row["tier"]),
                region=str(row["region"]),
                compliance_group=str(row["compliance_group"]),
            ),
            route=Route(path=str(row["route_path"])),
            time=TimeWindow(timestamp_utc=float(row["timestamp_utc"])),
            config=config,
        )
        inputs.append(inp)
        truths.append(str(row["ground_truth_version_id"]))

    return inputs, truths


def run_benchmark(resolver: Resolver, adapter_name: str) -> dict:
    """Run all scenario CSVs through the resolver and write summary JSON."""
    RESULTS_DIR.mkdir(exist_ok=True)

    all_outputs: list[ResolutionOutput] = []
    all_truths:  list[str] = []
    per_group:   dict = {}

    csv_files = sorted(SCENARIOS_DIR.glob("*.csv"))
    if not csv_files:
        print(f"[flagbench] No CSV files found in {SCENARIOS_DIR}.")
        print("[flagbench] Run the scenario generator first: python -m flagbench.generate_scenarios")
        return {}

    for csv_file in csv_files:
        inputs, truths = _load_scenarios(csv_file)
        outputs: list[ResolutionOutput] = []

        for inp in inputs:
            t0 = time.perf_counter()
            out = resolver(inp)
            elapsed_ms = (time.perf_counter() - t0) * 1_000
            out.resolution_time_ms = round(elapsed_ms, 4)
            outputs.append(out)

        group = csv_file.stem
        per_group[group] = {
            "n_scenarios":           len(outputs),
            "accuracy":              round(resolution_accuracy(outputs, truths), 4),
            "fallback_rate":         round(fallback_rate(outputs), 4),
            "latency_ms":            latency_percentiles(outputs),
            "compliance_violations": compliance_violation_count(outputs),
        }
        all_outputs.extend(outputs)
        all_truths.extend(truths)

    summary = {
        "adapter":          adapter_name,
        "total_scenarios":  len(all_outputs),
        "overall": {
            "accuracy":              round(resolution_accuracy(all_outputs, all_truths), 4),
            "fallback_rate":         round(fallback_rate(all_outputs), 4),
            "latency_ms":            latency_percentiles(all_outputs),
            "compliance_violations": compliance_violation_count(all_outputs),
        },
        "per_group": per_group,
    }

    out_path = RESULTS_DIR / f"summary_{adapter_name}.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"[flagbench] Results written → {out_path}")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FlagBench benchmark runner")
    parser.add_argument(
        "--adapter",
        choices=["reference", "unleash", "unleash_sim"],
        default="reference",
        help="Which resolver adapter to benchmark",
    )
    args = parser.parse_args()

    mod = importlib.import_module(f"flagbench.adapters.{args.adapter}")
    result = run_benchmark(mod.resolve, args.adapter)
    if result:
        print(json.dumps(result.get("overall", {}), indent=2))
