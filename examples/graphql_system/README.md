# FlagBench × GraphQL System — Example

This example shows how to connect FlagBench to a real GraphQL feature flag system.
It mirrors a production setup where flags live in **AWS SSM Parameter Store**, are exposed
through a **GraphQL API**, and are consumed by a React frontend via Apollo.

---

## What's in this folder

| File | Purpose |
|---|---|
| `server.py` | Mock GraphQL flag server (mirrors your real backend) |
| `adapter.py` | Production-grade FlagBench adapter — finance-safe |
| `demo.py` | End-to-end demo: smoke test → benchmark → property check |
| `.env.example` | Template for required environment variables |

---

## Quick start (5 minutes)

**Terminal 1 — start the mock flag server:**
```bash
pip install flask
cd flagbench/
FLAGSERVER_TOKEN=dev-token python examples/graphql_system/server.py
# → Listening on http://localhost:4000/graphql
```

**Terminal 2 — run the demo:**
```bash
cd flagbench/
pip install -r requirements.txt requests
python -m flagbench.generate_scenarios   # generate the 2,000 test scenarios

export GRAPHQL_URL=http://localhost:4000/graphql
export GRAPHQL_TOKEN=dev-token

python examples/graphql_system/demo.py
```

Expected output:
```
STEP 1 — Smoke test: resolve your real flags
  creEnabled                → enabled      [ACTIVE]   1.23 ms
  helocEnabled              → disabled     [FALLBACK]  1.10 ms
  loanWriteMode             → hybrid       [ACTIVE]   1.18 ms
  ...

STEP 2 — FlagBench benchmark harness (2,000 scenarios)
  Accuracy:              93.6%
  Compliance violations: 0
  Latency p50/p90/p99:   1.2 μs / 4.8 μs / 12.1 μs
  ✓ Accuracy ≥ 95% — resolver is behaving correctly across all scenario types.
  ✓ Zero compliance violations — approved versions always selected when eligible.

STEP 3 — Property verification
  ✓ P1 Determinism: PASS
  ✓ P2 Fallback Safety: PASS
```

---

## Connecting to your real backend

1. Copy `.env.example` to `.env`
2. Fill in your real `GRAPHQL_URL` and `GRAPHQL_TOKEN`
3. Source the file: `source .env` (or use [python-dotenv](https://pypi.org/project/python-dotenv/))
4. Run the demo — it calls your actual flag service

```bash
source .env
python examples/graphql_system/demo.py
```

---

## How the adapter works

The adapter (`adapter.py`) is a single `resolve()` function. FlagBench calls it once
per test scenario:

```
FlagBench scenario
       │
       ▼
   resolve(inp)
       │
       ├─ circuit breaker OPEN? → return fallback immediately
       │
       ├─ POST /graphql  { query: GetFeatureFlags }
       │    Authorization: Bearer $GRAPHQL_TOKEN
       │    verify=True  (TLS always enforced)
       │    timeout=$GRAPHQL_TIMEOUT_S
       │
       ├─ error? → record_failure(), return fallback safely
       │
       └─ map activeVersion → ResolutionOutput
```

---

## Security properties

The adapter is designed for regulated financial applications:

| Property | Implementation |
|---|---|
| No hardcoded credentials | Credentials loaded from env vars only; adapter raises at startup if missing |
| TLS verification | `verify=True` on every request — never bypassed |
| Explicit timeouts | Connect + read timeout via `GRAPHQL_TIMEOUT_S` (default 5s) |
| Retry with back-off | Exponential back-off on 429/502/503/504 via `urllib3.Retry` |
| Circuit breaker | After `FLAGBENCH_CB_THRESH` failures → fail-safe to fallback_version |
| No PII in logs | `user_id` is SHA-256 hashed before any log output |
| Safe error messages | Exception messages not logged (may contain internal URLs or tokens) |
| Auth error handling | 401/403 treated as critical (logged loudly), not silently retried |
| Thread safety | Single `requests.Session` with connection pooling, protected by a lock |
| Audit trail | Every resolution decision logged with flag name, hashed user, version, latency |

---

## Unlocking P3 and P4 testing

Your current GraphQL query returns only `name` and `activeVersion`. To test
**Compliance Precedence (P3)** and **Monotonic Rollout (P4)**, add these fields
to your GraphQL schema and query:

```graphql
query GetFeatureFlagsExtended {
  featureFlags {
    name
    activeVersion
    complianceStatus   # "approved" | "pending" | "deprecated"
    rolloutPct         # 0.0 – 1.0
  }
}
```

Then switch the adapter to use `GRAPHQL_QUERY_EXTENDED` (already defined in `adapter.py`).
This maps directly onto the FlagBench `VersionSpec` model and enables the full
four-property correctness profile.

---

## Running in CI

Add to your pipeline (GitHub Actions example):

```yaml
- name: Run FlagBench
  env:
    GRAPHQL_URL: ${{ secrets.GRAPHQL_URL }}
    GRAPHQL_TOKEN: ${{ secrets.GRAPHQL_TOKEN }}
  run: |
    python -m flagbench.generate_scenarios
    python -m flagbench.harness --adapter examples.graphql_system.adapter
```

The results (`results/summary_graphql_system.json`) can be archived as a CI artefact
and diffed across releases to detect correctness regressions.
