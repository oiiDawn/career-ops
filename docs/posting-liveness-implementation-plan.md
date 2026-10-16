# Periodic posting liveness: implementation plan

Status: technical proposal, 2026-10-16. Business decisions are recorded in [ADR 0003](adr/0003-posting-liveness-is-maintained-independently.md). No runtime or scheduler changes are part of this document.

## Outcome and ownership

Hermes invokes a dedicated command at 06:00 and 18:00 Asia/Shanghai. Python selects unsubmitted candidate opportunities, persists observations and decides whether deletion is justified. The existing Node adapter reads public ATS APIs and falls back to Playwright. No model call, new scheduler, external service or generic workflow framework is needed.

An absent, stale or failed liveness check never gates evaluation, application preparation, recommendations or notifications. Missing or invalid JD evidence can still prevent evaluation for its own reason. Explicitly confirmed closure is the only liveness result that changes business workflows: it initiates deletion of an unsubmitted opportunity.

## Verified implementation surfaces

| Surface | Current implementation | Required change |
| --- | --- | --- |
| Selection and command | `career_ops/discovery/liveness_check.py`: selects candidate URLs, prints results, writes nothing | Retain read-only checking; add explicit persisted maintenance mode |
| Collection | `adapters/node/browser/_liveness-observe.mjs`: reuses API/browser readers, writes one final JSON batch, drops observation codes | Emit validated per-posting results as they complete, including evidence and codes |
| Classification | `liveness-api.mjs`, `liveness-browser.mjs`, `liveness-core.mjs` | Cover LinkedIn's observed closure wording; distinguish explicit closure from weak expired heuristics |
| Scan source | `tasks.py`: capture freshness currently determines `source.liveness`; uncertain sources wait before extraction | Separate usable JD evidence from liveness and remove only liveness-dependent waits/refreshes |
| Extraction and score | `model.py`, `evaluation/scan_graph.py`, `input_contracts.py`, `evaluation/score_graph.py` | Remove model liveness judgments, active-only gates and fabricated active evidence |
| Display | `dashboard/data.py` and `dashboard/index.html`: reads liveness and reason from retained scan artifacts | Read the maintained observation and display its time and freshness |
| Persistence | `db.py`, `discovery/store.py` | Add observations and transactional closure/deletion methods; preserve shared facts |
| Discovery | `configured.py`, `reverse_runner.py` and shared `DiscoveryStore.ingest` | Enforce closed-URL suppression at write time as well as run-start deduplication |
| Task/application writes | `BusinessStore.start`, task resume/publication and application lifecycle commits | Reject writes against removed/confirmed-closed opportunities; serialize with deletion |

The repository has no `.codegraph` directory. These findings come from source and a read-only inspection of the current SQLite schema, not from runtime acceptance tests.

## Observation storage and display

Add one append-only `liveness_observations` table to `data/opportunities.db`, owned by the business store. Fields: observation ID, opportunity ID, original posting URL, UTC observation time, result (`active`, `expired`, `uncertain`), stable reason code, API/browser method and structured evidence JSON. Index `(opportunity_id, id)` for latest-result lookup. Keep `expired` as the existing adapter value; the user-facing term is closed.

Evidence includes the checked source URL, final URL where available, response status, posting identity and a bounded relevant source excerpt or provider status. Check errors are observations with `uncertain` and a diagnostic code, never closure evidence. Validate types, result codes and requested-posting identity at the Python boundary before persistence. Do not accept a reason string alone as a deletion instruction.

The latest observation determines the display. An active observation older than 24 hours displays as uncertain. A newer failed check also displays as uncertain; show its check time and the last successful active confirmation separately. Missing observations display as uncertain. Dashboard list, detail and filters use this same projection, without modifying immutable historical reports or making them appear newly checked.

An observation received for a removed opportunity or a changed URL is discarded. Do not update by numeric ID alone: `opportunities.id` can be reused after deletion.

## Collection, isolation and command

Keep `career_ops system liveness` read-only by default, including explicit URL/file diagnostics. Add `--apply` for the real current-opportunity maintenance consumer; require database-backed selection in that mode so arbitrary diagnostic URLs cannot trigger unrelated deletion.

The maintained collector streams one JSON observation per completed URL over stdout; diagnostics go to stderr. Python consumes and commits each valid line before continuing. Reuse the current API/browser readers and browser session; catch failures per URL and recreate a broken browser page when necessary. A later process crash or malformed record cannot erase previously committed observations. Bound each request and the overall process, terminate a timed-out child and preserve prior progress. Do not hold a SQLite write transaction while waiting for network I/O.

A single nonblocking liveness-maintenance process lock prevents overlapping scheduled/manual maintenance runs. It is separate from score, application and discovery locks. Individual uncertain results are normal outcomes; report collection/storage failures after processing remaining work. Expected closures are not command failures. Keep read-only diagnostic exit semantics separate from maintenance semantics.

Add `scripts/career-ops-liveness.sh` invoking `.venv/bin/python -B -m career_ops system liveness --apply --no-fallback --throttle=5000`. Scheduled runs use headless fallback, without opening an interactive browser window. Retain existing provider-specific throttling, including LinkedIn's API throttle. No tight retry loop: retry failures at the next regular run or by manual maintenance.

## Explicit closure boundary

Automatic deletion requires a validated result for this specific posting and an explicit closure signal, such as an identity-bound closure banner or a provider endpoint whose per-posting gone status is authoritative. Add the observed LinkedIn wording `Not currently accepting applications` to both applicable API and browser paths.

Do not delete solely because `result == expired`: existing classifiers also use that value for listing-page redirects, error-query URLs and absence from an org-level listing. Those signals do not meet the agreed deletion standard. Preserve useful existing adapter behavior for discovery, but require explicit evidence in the new destructive consumer. Network failures, generic 404 pages after redirects, missing controls, challenges, conflicting posting identity and missing search results remain inconclusive for deletion.

## Safe deletion and rediscovery

Reuse `scan_outcomes` with `status=skipped_expired` for minimal closed-URL suppression. Match the existing canonical URL key. Keep only URL, closure code and check time after cleanup; do not retain the full deleted opportunity as an archive.

Deletion proceeds as follows:

1. Acquire nonblocking locks for relevant task executions, then start a short `BEGIN IMMEDIATE` transaction. Re-read opportunity identity, current closure evidence, application state and lifecycle facts. Submission always wins: if already submitted, keep the opportunity and do not apply this deletion policy.
2. If an execution is genuinely active, record confirmed closure and defer destructive cleanup. Prevent new tasks for this confirmed-closed opportunity; finish cleanup on the next regular maintenance run after execution releases it. A persisted `running` flag alone does not prove a live process: reuse task locks to distinguish crashed execution. Do not kill active model work or delete files it is writing.
3. Within the transaction, persist closed-URL suppression and a temporary cleanup manifest, then remove dependent business rows and the opportunity. Capture task/result IDs and owned artifact paths before removing references. Roll back the whole business transaction on failure.
4. After commit, remove only exclusively owned files and matching outer workflow checkpoint threads. Use the installed `SqliteSaver.delete_thread()` rather than deleting its tables wholesale. Record unfinished cleanup in the manifest and retry it at the next run; remove manifest paths and task IDs after success so only the minimal closed-URL record remains.

Business deletion and filesystem/other SQLite deletion cannot be one atomic commit. The manifest is therefore necessary crash recovery for the authorized physical deletion, not an optional background service. Store it temporarily in the existing closed outcome payload; a second queue or deletion framework is unnecessary.

Cleanup must cover actual FK and non-FK references: task context/events/results and `job_company_profiles`; workflow source evidence; notification records; application records; interview child records and tasks; source/page/repost evidence; opportunity events and observations; eligibility/evaluations; artifact references; business checkpoints and deliveries. Delete children before parents. Preserve shared `company_ratings`, company-profile evidence, candidate source documents and any file still referenced by another opportunity or task.

File candidates include `data/artifacts/<task-id>/`, the corresponding `workflow-drafts/<input-hash>/` directories, JD cache entries under `data/cache/scan-jds/`, and matching threads in `workflow-checkpoints.db`. Derive paths from actual references and frozen inputs; do not glob by opportunity number or delete whole cache/checkpoint stores. Resolve paths, verify managed ownership, avoid following symlinks out of managed storage, and recheck shared references before removal. Preserve anything whose ownership cannot be established and report incomplete cleanup.

Close the write races in existing owners:

- `DiscoveryStore.ingest` must recheck the latest closed outcome inside its insertion transaction. Both configured and reverse discovery currently rely on run-start snapshots and can otherwise recreate a deleted URL. Update publishing callers and summary counts for a suppressed insert.
- Task start, resume and final publication must verify the bound opportunity still exists and is not confirmed closed inside their write transactions. Old waiting tasks and checkpoints cannot recreate a deleted opportunity. Coordinate active task locks with deletion in a deterministic order and handle removed-task results without masking them with a second lookup error.
- Application submission must check existence and commit its lifecycle transition in the same transaction used to compete with deletion. A stale form/action cannot add orphan application facts after deletion.
- Notification and material actions must revalidate the opportunity before acting; a deletion-pending closed opportunity cannot start new outward actions. This applies only to confirmed closure, never uncertain checks.

New URLs remain discoverable. Minimal URL suppression carries no company-role block. Same-URL reopening is a manual operation that must explicitly recheck and clear the closed outcome before re-ingestion; read-only URL inspection alone does not clear it.

## Scoring and retained data

Use one JD-usability rule across discovery-to-scan, explicit evaluation, scheduled advance and waiting-task resume: valid posting identity, retained capture integrity and substantive complete JD evidence. A capture becoming 24 hours old is not itself a liveness failure or a reason to fetch the same JD again. Fetch when evidence is missing or unusable; never turn a failed liveness check into invalid JD evidence.

Remove liveness-driven early returns in `Runtime.evaluate`, scan extraction/exclusion, score/apply input validation and scheduled selection/resume. Remove liveness assessment from the model prompt, response parsing and synthetic score evidence. Preserve completeness, identity, hash, actual eligibility and prescreen checks; an error page or search snippet must not become a scoreable JD.

Newly produced scan/report evidence should describe JD capture and its provenance without asserting current liveness. Maintain existing immutable reports and frozen task payloads as historical data; their liveness fields cannot control present-day status or block processing. Keep the existing input-integrity checks over frozen payloads and do not rewrite stored hashes.

A read-only inventory on 2026-10-16 found 145 waiting scan tasks, 7 waiting score tasks and 3 waiting apply tasks. Existing inputs include 253 score and 7 apply envelopes containing `jd_report_v1` with historical liveness fields, plus scan inputs with and without `source_contract_version=3`. These are real retained consumers, so a blanket schema rejection or global policy-version bump would disrupt valid work.

The proposed narrow transition keeps existing report schema names and accepts the existing frozen dictionaries unchanged; validators stop requiring or gating on liveness fields. New producers omit obsolete liveness judgments. Old extra fields remain historical data and are included unchanged when checking existing input hashes; do not strip them on read. Waiting tasks can use their existing complete JD evidence, subject to the normal integrity and candidate-policy checks. Invalidate only inner scan extraction cache entries whose saved control flow contains obsolete liveness waits/exclusions, using an extraction-contract cache revision, so resumption does not replay that old decision. Completed scores/reports are not rewritten or bulk rescored. Cover old-shaped frozen inputs and new-shaped inputs in tests before accepting this transition.

## Implementation slices and verification

| Slice | Deliverable | Necessary verification |
| --- | --- | --- |
| 1. Observe and persist | Evidence-rich per-URL collection, nonblocking maintenance, current display | API/browser classification tests; a later URL timeout/process crash preserves earlier commits; stale and failed display never changes eligibility or actions |
| 2. Confirm and delete | Transactional purge, cleanup recovery, write-time URL suppression | Isolated real-schema DB with scores/materials/shared artifacts; submitted protection; discovery/submission/task races; restart after DB commit before file cleanup; FK integrity and no reused-ID residue |
| 3. Decouple evaluation | Remove liveness gates and duplicate capture; preserve JD validity and historical results | A complete retained JD proceeds under missing/stale/failed checks without liveness network calls; invalid JD still waits; apply/notify remain usable; frozen hashes/history preserved |
| 4. Operational integration | Wrapper, CLI/operations docs and deployment instructions | `node scripts/check-syntax.mjs`; `.venv/bin/python -B tests/business/workflow-scan-test.py`; narrow liveness/discovery/dashboard/lifecycle/notification tests; actual CLI on an isolated store |

Complete and commit slices separately. Slices 1–3 must all pass before installing the schedule; a partially connected observer must not enable deletion against unprotected writers.

Use retained fixture pages for the exact LinkedIn closure case, then verify an approved live sample without destructive writes. Test actual adapters and actual SQLite commits as well as injected errors. Fixtures and passing tests alone do not establish current live-site access or correct destructive behavior.

Deployment is separate from this planning task. At cutover, inspect current Hermes jobs and in-flight writers, pause affected schedules briefly, take a consistent recoverable SQLite backup, validate the integrated code against a database copy, and inspect the first check's exact deletion candidates/evidence before production maintenance. Do not delete from stale historical liveness fields. Install the dedicated job only after implementation/deployment authorization, verify scheduler timezone and installed script, restore existing jobs, and inspect plain `hermes cron list` plus persisted per-posting results. A successful scheduler exit alone is not acceptance evidence.
