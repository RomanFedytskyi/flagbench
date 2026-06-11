# FlagBench

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![CI](https://github.com/RomanFedytskyi/flagbench/actions/workflows/ci.yml/badge.svg)](https://github.com/RomanFedytskyi/flagbench/actions)

> A property-based correctness benchmark suite for runtime feature flag resolution systems.
> Plug in any resolver — get a formal correctness profile.

Feature flag resolution systems are critical production infrastructure, yet no standardized
correctness specification or cross-system benchmark exists. FlagBench formalizes four
correctness properties and provides a reproducible benchmark suite any resolver can be
evaluated against.

---

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/RomanFedytskyi/flagbench.git
cd flagbench
pip install -r requirements.txt

# 2. Run all tests (unit + property-based oracle)
pytest tests/ flagbench/oracle.py -v

# 3. Run benchmark against the reference resolver
python -m flagbench.harness --adapter reference
```

Expected output from step 3:
```json
{
  "accuracy": 1.0,
  "fallback_rate": 0.0,
  "latency_ms": { "p50": ..., "p90": ..., "p99": ... },
  "compliance_violations": 0
}
```

---

## What FlagBench tests

FlagBench checks four formal correctness properties against any resolver:

| Property | Definition |
|----------|-----------|
| **Determinism** | Identical `(user, route, timestamp)` input always produces the same version output |
| **Fallback safety** | When no version satisfies constraints, the declared fallback version is returned |
| **Compliance precedence** | An `approved` version is always selected over `pending`/`deprecated` when eligible |
| **Monotonic rollout** | Increasing a version's rollout percentage never decreases its selection frequency |

These properties are derived from the formal model v = f(u, r, t) published in:
> Fedytskyi, R. (2025). *Dynamic Frontend Architecture for Runtime Component Versioning
> and Feature Flag Resolution in Regulated Applications.* Software, 4(4), 32.
> https://doi.org/10.3390/software4040032

---

## Benchmarking your own flag system

### How it works

FlagBench does **not** replace your flag system. It tests it.

You already have code somewhere in your app that resolves a feature flag — something like:

```python
# what you already have in production today
variation = ldclient.variation("checkout-widget", user, default="v1")
# or
variant = unleash.get_variant("checkout-widget", context)
# or
version = my_api.resolve_flag(flag="checkout-widget", user_id=user.id)
```

FlagBench needs to call that same code 2,000 times with different test inputs and record the results. The way you connect FlagBench to your system is by writing a small **adapter** — a single `resolve()` function that:

1. Receives a test scenario from FlagBench (user, route, timestamp, available versions)
2. Calls your existing SDK/API exactly like your app does
3. Returns the result back to FlagBench

Think of it as a translator between FlagBench's test format and your system's API. **You don't implement any new API — you just wrap the one you already have.**

```
FlagBench                     Your system
─────────────────             ──────────────────────────────────
sends test scenario  →  resolve()  →  your_sdk.get_variant(...)
                     ←             ←  returns selected version
records the result
```

### Step 1 — Write the adapter (one file, ~20 lines)

Create `flagbench/adapters/my_system.py` and inside it call your SDK:

```python
from flagbench.schema import ResolutionInput, ResolutionOutput

def resolve(inp: ResolutionInput) -> ResolutionOutput:
    # Call your existing flag system here.
    # inp.config.component_id   = the flag/toggle key (e.g. "checkout-widget")
    # inp.user.user_id           = the user being evaluated
    # inp.config.fallback_version = what to return if the flag is off/unavailable
    # inp.config.version_set     = all known variants with compliance metadata

    result = your_sdk.get_variant(
        flag_key=inp.config.component_id,
        user_id=inp.user.user_id,
    )

    # If your system returns nothing / flag is off → use the declared fallback
    if result is None or result.is_disabled:
        fb = inp.config.fallback_version
        return ResolutionOutput(
            version_id=fb.version_id,
            is_fallback=True,
            compliance_status=fb.compliance_status,
        )

    # Otherwise look up the full metadata for the selected variant
    selected = next(
        (v for v in inp.config.version_set if v.version_id == result.name),
        inp.config.fallback_version,
    )
    return ResolutionOutput(
        version_id=selected.version_id,
        is_fallback=False,
        compliance_status=selected.compliance_status,
    )
```

### Step 2 — Run the benchmark

```bash
python -m flagbench.harness --adapter my_system
# → writes results/summary_my_system.json
```

### Step 3 — Run the property checks

```bash
pytest flagbench/oracle.py -v --hypothesis-seed=0
# → writes results/properties_my_system.json
```

### What you get back

```json
{
  "overall": {
    "accuracy": 0.94,
    "compliance_violations": 47,
    "latency_ms": { "p50": 1.2, "p90": 4.8, "p99": 12.1 }
  }
}
```

- **accuracy** — how often your system returns the correct version (vs. the formal model)
- **compliance_violations** — how many times a `pending`/`deprecated` version was selected when an `approved` one was available (the most common regulatory risk)
- **latency** — end-to-end resolution time; p99 > 50 ms usually means an unintended network call inside the resolution path

### Don't have a flag system yet?

Just run the reference adapter — no setup needed:

```bash
python -m flagbench.harness --adapter reference
```

This benchmarks FlagBench's own built-in resolver (the formally correct one) and is how the paper results were produced.

> **Copy-paste adapters for LaunchDarkly, Unleash, and REST API systems → [docs/adapter_guide.md](docs/adapter_guide.md)**

---

## Benchmark dataset

| File | Scenarios | Tag | Tests |
|------|-----------|-----|-------|
| `normal_ops.csv` | 800 | SYNTHETIC | Typical user/route/time distributions |
| `boundary_conditions.csv` | 400 | DERIVED | Rollout 0%/100%, compliance transitions |
| `fallback_trigger.csv` | 400 | DERIVED | No version satisfies constraints |
| `adversarial.csv` | 400 | LITERATURE + SYNTHETIC | Known flag-system failure modes |

See `docs/scenario_provenance.md` for full provenance documentation.

---

## Reproducing paper results

```bash
python figures/plot_results.py
```

Generates Figures 1–4 from `results/` into `figures/`. All results are reproducible
from the scenario CSVs — no external services required.

---

## Citing FlagBench

If you use FlagBench in your research, please cite:

```bibtex
@software{fedytskyi2026flagbench,
  author  = {Fedytskyi, Roman},
  title   = {{FlagBench}: A Property-Based Correctness Benchmark Suite
             for Runtime Feature Flag Resolution Systems},
  year    = {2026},
  url     = {https://github.com/RomanFedytskyi/flagbench},
  license = {MIT}
}
```

A machine-readable `CITATION.cff` is included at the repository root.

---

## License

- **Code** (`flagbench/`, `tests/`, `figures/`): MIT — see [LICENSE](LICENSE)
- **Data** (`data/`): CC BY 4.0

## Contact

Roman Fedytskyi — fedytskyi@gmail.com · Issues and pull requests welcome.
