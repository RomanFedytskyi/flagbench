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

## Running against your own resolver

Implement the five-line adapter interface:

```python
# my_adapter.py
from flagbench.schema import ResolutionInput, ResolutionOutput

def resolve(inp: ResolutionInput) -> ResolutionOutput:
    # call your flag system here
    ...
    return ResolutionOutput(
        version_id=selected_version,
        is_fallback=False,
        compliance_status=status,
    )
```

Then run:
```bash
python -m flagbench.harness --adapter my_adapter
```

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
