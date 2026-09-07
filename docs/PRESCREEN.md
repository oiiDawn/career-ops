# Canonical Stage 0 pre-screen

`lib/prescreen-core.mjs` is the only Stage 0 rule engine. It consumes evidence already extracted from the complete JD and approved candidate sources; it never guesses facts from prose. `prescreen.mjs` adds JSON I/O and URL-keyed cache persistence.

## Input

```json
{
  "job": { "url": "https://example.com/job/1" },
  "candidate_source_hash": "hash of the candidate snapshot",
  "complete_jd": true,
  "assessment_complete": true,
  "gates": {
    "location": { "status": "pass|fail|unknown", "reason": "...", "evidence": "..." },
    "employment": { "status": "pass|fail|unknown", "reason": "...", "evidence": "..." },
    "company_size": { "status": "pass|fail|unknown", "reason": "...", "evidence": "..." },
    "compensation": { "status": "pass|fail|unknown", "reason": "...", "evidence": "..." }
  },
  "years": { "required": 0, "verified": 0, "evidence": "..." },
  "core_capabilities": [{ "name": "...", "core": true, "mandatory": true, "match": "proven|adjacent|gap|unverified", "evidence": "..." }],
  "credentials": [{ "name": "...", "mandatory": true, "status": "present|absent|unknown", "evidence": "..." }]
}
```

Use `0`/`0` when the JD states no minimum years. Empty capability/credential arrays mean the complete JD states none; a missing field means assessment is incomplete.

`company_size` is also a hard gate because this profile requires at least 50 employees. If the size is unavailable, use `unknown` and carry the exact verification question forward; do not fail it merely for missing data.

## Result and reuse

Every result carries `schema`, `schema_version`, `rules_version`, `input_hash`, `generated_at`, `status`, `discard_reasons`, `uncertainties`, and `missing`.

- `pass`: no hard failure or unresolved gate.
- `fail`: at least one auditable hard failure. Explicit failures win over missing/unknown fields.
- `uncertain`: complete assessment with unknown, adjacent, borderline, or unverified evidence. Unknown is never fail.
- `incomplete`: full JD or required assessment fields are missing.

Pipeline and batch reuse only schema-valid, hash-matching, non-`incomplete` records. Scan cannot guarantee a complete assessment and therefore writes `incomplete`. Liveness is a separate contract.
