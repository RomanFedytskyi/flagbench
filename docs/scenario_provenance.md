# Scenario Provenance

Each scenario in `data/scenarios/` carries one of three provenance tags:

| Tag | Meaning |
|-----|---------|
| `[DERIVED]` | Follows directly from a formal property definition |
| `[LITERATURE]` | Recreates a failure mode from a published post-mortem or bug report |
| `[SYNTHETIC]` | Generated to cover parameter regions not reached by DERIVED/LITERATURE cases |

## Per-group breakdown

| File | N | Tag | What it exercises |
|------|---|-----|-------------------|
| `normal_ops.csv` | 800 | SYNTHETIC | Typical production distributions of user tiers, routes, version sets |
| `boundary_conditions.csv` | 400 | DERIVED | rollout=0%, rollout=100%, compliance-status transitions at boundaries |
| `fallback_trigger.csv` | 400 | DERIVED | All versions fail eligibility → fallback must be returned |
| `adversarial.csv` | 400 | LITERATURE + SYNTHETIC | Known flag-evaluation failure modes from Unleash and LaunchDarkly issue trackers |

## Column definitions

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | string | Unique user identifier |
| `tier` | enum | `standard` \| `premium` \| `admin` |
| `region` | string | ISO-3166 alpha-2 country code |
| `compliance_group` | string | Compliance cohort label (`A`, `B`, `C`) |
| `route_path` | string | Application route, e.g. `/dashboard` |
| `timestamp_utc` | float | Unix timestamp |
| `component_id` | string | UI component being resolved |
| `version_ids` | string | Semicolon-separated version identifiers, e.g. `v1;v2;v3` |
| `compliance_statuses` | string | Semicolon-separated statuses (`approved`\|`pending`\|`deprecated`) |
| `rollout_pcts` | string | Semicolon-separated floats in [0.0, 1.0] |
| `stability_scores` | string | Semicolon-separated floats in [0.0, 1.0] |
| `active_version_id` | string | Declared active version |
| `fallback_version_id` | string | Declared fallback version |
| `ground_truth_version_id` | string | Expected output from reference resolver (used for accuracy scoring) |
