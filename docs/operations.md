# Local operations

Install dependencies with `uv sync --locked` and `npm ci`. The root `.venv`
is the Career Ops Python environment. Run `.venv/bin/python -B -m career_ops
--help`; each command has its own `--help`.

| Command | Purpose |
| --- | --- |
| `discover [global]` | Collect configured sources or sweep public ATS directories |
| `evaluate ID` | Scan and score a retained opportunity |
| `apply` | Prepare materials; record confirmed events, replies and salary; communication and prefill |
| `interview` | Preparation plans, stories and durable sessions |
| `cv` | Preview, confirm, recover and check candidate facts |
| `show ID` | Show an opportunity and its retained results |
| `list --view VIEW` | Opportunities (default), scores, decisions, applications or followups |
| `insights` | Aggregate retained evidence |
| `task` | Start explicit inputs; inspect, resume, run and cancel tasks |
| `dashboard` | Local page of scanned, scored and applied jobs; its only writes start `apply prepare` or a re-score of the retained JD (`--port`, default 8765) |
| `system` | Doctor, portal maintenance, liveness, company resolution, advance and notify |

Daily commands derive inputs from the opportunity ID:

```bash
.venv/bin/python -B -m career_ops list
.venv/bin/python -B -m career_ops evaluate 123
.venv/bin/python -B -m career_ops apply prepare 123
.venv/bin/python -B -m career_ops interview preparation-plan 123
.venv/bin/python -B -m career_ops task show TASK_ID
```

Discovery skips previously observed source posting URLs, including LinkedIn
locale, slug and tracking-parameter variants of one numeric posting ID. New
URLs reach a shared resolver inside the SQLite write transaction in both
configured and global discovery, including resumed runs. Company and title
alone never suppress an opening. Explicit employer `company_aliases` in
`portals.yml` only select candidates; different official requisitions remain
separate. Cross-source matching otherwise requires the same normalized title,
location and complete substantive JD, with numbers preserved. Missing evidence,
ambiguous matches and text similarity alone do not authorize a merge.

`scan_observations` retains confirmed source URL aliases for each opportunity.
Alternate source captures stay separate from the primary URL's capture and
cannot replace its JD, score or application status. Fingerprints use the final
captured JD and only warn about possible cross-listings. New-opening counts
survive a crash after ingestion and before run publication. Public captures in
`tests/fixtures/discovery-real-postings.json` exercise duplicate replay and
distinct-level, requisition, direction, domain and incomplete-JD boundaries.

Historical consolidations require reviewed identities, an SQLite backup,
opportunity execution locks, immutable archives of removed records and an
integrity check. Prefer an already submitted record; never choose between
conflicting submissions automatically. Preserve source aliases and the surviving
record's assessment and application state. Operational dedup archives and
backups live under `data/maintenance/`; they are not scoring inputs.

Use `task start scan|score|apply ID INPUT` for explicit input imports. Business
commands emit JSON by default. Put global sweep options after `discover global`.
`discover --throttle MS` takes milliseconds; zero disables the delay.
`system resolve-company` previews by default; `--write` and `--dry-run` cannot
be combined. Application events retain confirmation, source attribution and
idempotency requirements; preparing materials never records submission.

`--directory PATH` before the command selects the business store directory;
its default is `data/`. Interview context maps it to `opportunities.db`.
Read-only file tools do not use a business directory. Application preparation
never submits an application. New model calls and external sends require the
appropriate user authorization.

Personal data belongs in `inputs/`: `cv.md`, `profile.yml`, `targeting.md`,
`portals.yml`, `voice.md`, optional `article-digest.md`, `documents/`, `stories/`,
and `writing-samples/`. Copy example profile and fact constraints from
`docs/examples/` when setting up a fresh checkout; copy `portals.yml` there
to `inputs/portals.yml` for source configuration. `CAREER_OPS_INPUT_ROOT` may
select another input directory. Its sibling `rules/` holds scoring and workflow
policies. Inherited environment settings take priority over `.env`.

`rules/scoring.md`, domain policies, shared contract, and market rules retain
their existing bytes. Their historical path and command labels are stable
source labels in persisted inputs, not executable entrypoints. The context
manifest is also preserved as a record of those labels. Use this document and
the agent router for current command paths; editing frozen policies intentionally
invalidates affected results and waiting confirmations.

`data/opportunities.db` owns business facts, including CV task previews and
confirmations. `workflow-checkpoints.db` owns scan/score/apply/interview/delivery
execution progress; `cv-checkpoints.db` owns CV preview progress. Completed
business commits remain idempotent even if a process stops before checkpoint
save. CV file application verifies the confirmed preview, locks updates, and
recovers the same task after interruption.

Reports, captured sources, frozen payloads, PDFs, package manifests, and stored
absolute artifact references retain their existing physical locations and bytes.
They are not moved into a cosmetic new layout. Historical working directories
remain where referenced by checkpoint state or manifests. New operation paths
must not overwrite those artifacts. Explicitly authorized closure maintenance
removes exclusively owned artifacts of confirmed-closed, unsubmitted postings;
shared evidence and candidate source documents remain protected.

Hermes invokes `scripts/career-ops-scan.sh` and `scripts/career-ops-score.sh`;
installed copies under `~/.hermes/scripts/` must match. Scan collects discovery;
score advances existing evaluation tasks and uses the previously authorized
notification policy. Check `system doctor --json` and the offline suite before enabling
changed wrappers. Neither doctor nor offline fixtures send candidate data.

LinkedIn discovery uses the public `/jobs-guest/jobs/api/seeMoreJobPostings/search`
list endpoint with ten-record offsets. Each keyword can read up to 25 pages
(250 positions); health probes retain their one-page limit. The final list URL
must preserve the endpoint and all query parameters. A successful empty fragment
(whitespace, doctype or comments only) ends that list; unreadable shells and
login/challenge responses remain failures. Repeated
pages are detected by the same keyword's posting ID sets; cross-keyword job
deduplication does not stop pagination.

LinkedIn discovery retries a rate-limited search or detail request at most twice,
waiting 10 then 20 seconds. A longer `Retry-After` increases the wait; if it exceeds
60 seconds, skip that request rather than retrying before the server allows it.
Exhausting retries skips the failed detail or search keyword
without clearing the other queued work. Waits, navigation pacing and browser
reads share the source deadline: each LinkedIn source has a twenty-minute budget
with 1,125 seconds available for collection and a 75-second reserve. Other
configured providers keep their ten-minute budgets. Both the Node collector and
the enclosing Python process allow the extended LinkedIn deadlines. A retry that cannot
fit ends collection with partial results. For search providers, a detail HTTP403
is reported and skipped without retrying or discarding other queued postings.
HTTP401/405 still stop that source.

The enabled `LinkedIn — Xi'an` job board searches `Xi'an, Shaanxi, China` across
all employers, using the shared profile keywords and up to 200 complete postings.
Its `search.posted_within_days: 30` selects the last thirty days; other LinkedIn
sources default to seven days. This source uses no employer filter. Normal
posting filters, deduplication and qualification checks still apply after collection.

The ten-minute score schedule selects retained unscored postings as well as scores
marked `needs_rescore` (待重新评分). `refresh_reasons` distinguishes changed scoring
inputs from expired company evidence; either cause enters the same refresh queue.
`list --view scores` exposes both fields; `list --view decisions` separates ready
`decisions` from the `needs_rescore` list.
Dashboard keeps the decision derived from the latest retained scores visible while
marking it 待重新评分; refresh eligibility does not erase the previous decision.
Refresh reuses the hash-verified retained JD and reruns prescreen only when its
inputs changed. Current company evidence remains reusable; expired evidence is
researched again. The evidence request date changes the execution identity without
invalidating otherwise current numeric scores when a new day begins.

Waiting evaluation tasks are replaced when candidate/policy inputs or usable JD
content change. Their old frozen inputs and completed results remain intact.
Unchanged incomplete-evidence waits require new evidence; transient failures get
one automatic retry. Missing-source probes run at most once per day, unless new
retained evidence becomes available. Failed application preparation does not block
independent evaluation. `idle / no_runnable_evaluations` means no task can currently
advance, including when unresolved waits remain; it does not mean every job is scored.

`evaluate ID` and `system advance` trace one opportunity as `job-evaluation`,
with `prescreen` and `score` stages under the same root. A scheduled run continues
from a completed prescreen into scoring; exclusions or waiting conditions stop it.
The persisted task module `scan` identifies the prescreen stage and retains its
existing checkpoint and evidence keys. Batch source collection is `discovery`.

Model calls run inside the LangGraph nodes with settings from `.env`. When the
Langfuse settings are present, every top-level graph run becomes one trace in the
local Langfuse (`~/dev/langfuse`, http://localhost:3001) with full node inputs,
outputs and model prompts; nested scan/score/apply graphs appear inside their
task's trace. `scripts/check.py` disables tracing; an offline Langfuse never
blocks a workflow.

JD capture cache lives at `data/cache/scan-jds/` and is reused for at most 24 hours.
Intact identity-bound retained JD evidence is reused by evaluation regardless of age; the cache expiry does not trigger a liveness recheck.
Retained source evidence belongs to the business store and referenced artifacts.
Unreferenced acceptance output, expired captures and old tracker-import batches
are removed without an archive.

## Company research and scoring

Run `.venv/bin/python -B -m career_ops task start score ID scan:ID --re-evaluate`
for a retained complete JD. A deterministic lookup reuses retained employer identities and constructs region/grade scopes from official location fields and explicit role titles, without a model call. Missing fields remain unknown; ambiguous retained identities stop scoring. New employers use the posting host as an identity lead and the posting URL as a research seed.
One Codex CLI task researches all missing company/culture/compensation scopes together, using
`gpt-6.1-sol`, low reasoning and live web search, with a 900-second process deadline.
The CLI must be installed and authenticated with `codex login` under the scheduler's user.
`system doctor` checks CLI availability and login status. PATH discovery also supports the bundled
macOS desktop CLI when the scheduler has a smaller PATH.

Research uses an ephemeral read-only working directory, ignores user configuration and receives
only public employer information and retained public job descriptions. Project API keys, private
candidate sources and the scoring rubric are excluded from its environment and prompt. Instructions
forbid skills and non-research actions. A native `company-research` permission profile denies filesystem
reads outside the working directory except minimal OS runtime paths, denies writes and command network
access, and keeps hosted live web search available. Shell tools, connectors, plugins, browser control,
hooks, memories and subagents are disabled; project instructions are not loaded. Saved CLI authentication
remains accessible to the CLI harness, not sandboxed commands. Shared topics and evidence rules live in
`career_ops/evaluation/codex_research.py`. No personal preferences enter research.

Codex returns sourced fact arrays. JSON structure, exact requested profile IDs and HTTP source URLs
are validated before Jev receives anything. Empty facts remain unscored. Same-employer policies,
other-team experiences and salary reference levels can inform screening with their actual scope
and limitations; they never become guaranteed job conditions. Only plausible public research
questions remain in gaps. Unknown is not evidence of absence.

`data/company-profiles` retains the public prompt, schema, command, CLI events, stderr, original
fact output, elapsed time, available token usage and immutable scoped archives/ratings. Tool events
and citations are source references, not guaranteed complete webpage-body captures. Failed or timed-out
runs retain diagnostics, produce no new fact archive and have no model fallback. A later workflow
attempt starts a new isolated Codex task; completed evidence and Jev ratings are reused.

Local Langfuse records the Codex task as one aggregate generation with its public prompt, final output
and reported token usage. Each dispatched Jev HTTP attempt has its own generation with the request,
validated response or error, and provider-reported input/output token usage. Jev requests use the
official TypeSafe Python SDK with its internal retries disabled; the retained workflow owns the
single retry and captures every raw HTTP response through the SDK's HTTP client. Codex cache reads and
writes are separate input categories; its multi-turn aggregate cannot establish per-request long-context
pricing, so its cost is a Standard API equivalent estimate, not a subscription charge. These inherit the owning score graph's
trace. Cached results create no model generation. The callback requires the explicit `langchain`
dependency; `system doctor` checks its import as well as local server health. Codex's individual web
tool calls remain in the retained CLI events rather than separate Langfuse observations.

The local project's model prices were verified on 2026-10-09 (USD per million tokens):

| Model | Uncached input | Cached input | Cache writes | Output, including reasoning |
| --- | --- | --- | --- | --- |
| `jev-1.13.0` | 0.042 | — | — | 0 |
| `gpt-6.1-sol` Codex (ChatGPT account login) | not verified | not verified | not verified | not verified |
| `deepseek-v4.1-flash`, configured peak rates | 0.30 | 0.006 | — | 1.20 |

Sources: [TypeSafe](https://docs.typesafe.ai/models) and
[DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/).
DeepSeek off-peak rates are half the configured peak rates; peak hours are weekdays
01:00–04:00 and 06:00–10:00 UTC, excluding Chinese public holidays. The current model
definition uses peak rates, so off-peak observations need a separate cost reconciliation.
OpenAI's long-context premium is based on each request's input, not Codex's cumulative
CLI total. The custom Codex aggregate definition uses Standard API prices only; it cannot
infer long-context premiums, service-tier premiums, tool fees, or subscription billing.
Langfuse v4 observations are immutable after ingestion. Historical corrections are attached
as annotations and audit spans; they do not replace the original dashboard totals.

Run `.venv/bin/python -B scripts/eval-company-research.py --output /tmp/company-research-eval`
to exercise the actual macOS sandbox with synthetic files. Add `--live` to research Microsoft and
GitLab with synthetic prompt-injection fixtures. This writes no business data. `results.json` records
permission/tool/leakage checks and facts for manual source-support and applicability review;
passing structural checks does not mark claims as semantically verified.

Company archives expire at the end of fixed 28-day windows anchored on 2026-10-12 (at most 28 days). Exact scopes and unchanged research rules
reuse facts, including empty results; new scopes collect only missing ranges. Changed research rules
or expiry require new research. Scoring-rule changes only rerun Jev. Existing archived evidence is
historical and does not become current merely because the caller extends a date.
Expiry dates are retained in frozen inputs but excluded from score freshness comparisons: changing
the expiry policy or crossing a window changes archive expiry, without itself making scores stale.
Profile discovery keywords and the application postal code do not invalidate scans
or scores. Frozen inputs and application packages still retain the full profile;
changes to role preferences, location, compensation and other evaluation inputs
continue to require a fresh evaluation.

Each nonempty dimension then receives one Jev request (multiple salary scopes share a request).
The existing `.env` `TYPESAFE_API_KEY` authorizes Jev 1.13.0; only this scoring stage receives
private thresholds. Raw requests/responses, finite transport retries, native decimals, confidence
and independent screening-reference sufficiency are retained. Direction is evaluated per job.
SQLite company ratings and per-result references, input checks, report publication and Dashboard
remain on the existing workflow. Research dispatches count once in task usage; CLI aggregate token
usage is retained separately and is not an internal model-request count or a monetary bill.

Initial recommendations use four scores: all must be strictly above 3 and at least two strictly above 4 for `focus`; other/missing scores
are `deprioritize`, and confirmed hard failures remain `discard`. Confidence and sufficiency are
informational and never trigger automatic review or fallback. Full scoring also includes employer lookup, direction and report generation; the 900-second cap applies to each Codex research task.

Recommendation-only policy edits do not invalidate numeric scores. Stored scoring inputs remain byte-hash verified; freshness compares the scoring rubric independently of its two recommendation paragraphs. A report format change keeps no compatibility for earlier reports; re-evaluation writes them anew. Current decisions and Dashboard derive the current policy from retained scores.

## Independent posting liveness

`system liveness` remains read-only, including explicit URL and `--file` diagnostics.
`system liveness --apply --no-fallback --throttle=5000` maintains the current
unsubmitted candidate pool, including already scored opportunities. `--apply`
cannot be combined with diagnostic URLs or files. It uses public ATS APIs first,
then a headless browser; no model is called. Each observation is committed as it
arrives, so a later failed URL or collector crash cannot erase earlier results.

SmartRecruiters requires a matching posting ID, explicit public/active fields and
a matching application URL. HKSTP requires a matching posting ID, explicit active
status and a current publication period; API failures cannot establish closure.
Browser checks recognize localized LinkedIn controls
and closure text, SmartRecruiters application links and Mercedes-Benz custom
buttons. Hidden or disabled controls cannot establish activity. Inconclusive
pages receive up to six extra seconds to hydrate; generic missing-page messages
remain uncertain because Workday also displays them after permission failures.
Each retry reads the main document and same-origin posting frames together. The
classifier returns its matched closure excerpt directly; browser collection does
not maintain a second closure rule list. Generic closure dates or application
closure text without a posting-specific assertion cannot authorize deletion.

Per the user-confirmed LinkedIn rule, a fully rendered matching job detail page
without a visible Apply control is closed. This requires a matching canonical
posting ID, a visible job title and description, a completed hydration wait and
no login wall. A dismissible LinkedIn sign-in prompt is closed through its own
button before checking; mandatory login walls remain uncertain.
Missing guest-API signals trigger this browser check; conflicting
closure/application signals remain uncertain. HTTP errors, partial pages and
identity mismatches cannot establish this closure.

Eightfold detail pages without an Apply control may use their public API to
resolve one trusted SuccessFactors application page. Activity requires a matching
ATS job ID in the API, destination URL and rendered heading, plus a visible Apply
control. A stale application URL alone cannot establish activity.

The maintenance command stores observations in `data/opportunities.db` and reports
per-posting results/errors as JSON. Normal uncertain observations and successful
closures are not command failures. Collection/storage/cleanup errors are reported
after other work is processed and produce a nonzero exit. An overlapping maintenance
run returns `busy` without affecting other workflows.

Dashboard liveness comes from these observations, with check time and last active
confirmation displayed. Missing results, checks older than 24 hours, and newly failed
checks display as uncertain. None of these conditions blocks evaluation, material
preparation or notifications. A complete, identity-bound JD is still required;
posting availability and JD evidence completeness are separate responsibilities.
Historical reports and frozen payloads are not rewritten or bulk rescored.

Explicit posting-bound closure initiates deletion of an unsubmitted opportunity
and its exclusive reports, drafts, captures and execution records. Submitted
applications, candidate source files and shared company evidence are protected.
Generic listing redirects, missing Apply controls outside the confirmed LinkedIn
rule, search absence and access failures cannot authorize deletion. Running work is not interrupted: confirmed
closure prevents new work, and cleanup retries after the active execution releases
its opportunity lock. `maintenance_status` distinguishes deletion, deferred work
and pending physical cleanup in a newly checked closed posting's output.

Closed URLs retain a minimal `skipped_expired` outcome for write-time discovery
suppression. A new URL is still discoverable. Physical files and workflow checkpoint
threads cannot be committed atomically with the business database: a temporary
manifest in the closed outcome permits retry at the next maintenance run. Shared
references are rechecked before deleting files; unowned paths are preserved and
reported. Same-URL reopening requires an explicit manual recheck and clearing the
closed outcome before re-ingestion; merely inspecting a URL does not clear it.

The dedicated entrypoint is `scripts/career-ops-liveness.sh`, installed identically
under `~/.hermes/scripts/`. Hermes job `9c81e6e28ec3` runs once daily
at 05:00 Asia/Shanghai, one hour before the 06:00 discovery run,
with this repository as working directory,
`no-agent` execution and local output. `hermes cron doctor` passed for all three
active jobs; existing discovery and scoring schedules were preserved.

The first production maintenance run checked 236 postings: 166 active, 43 uncertain
and 27 explicitly closed and deleted, with no run errors or pending cleanup.
Acceptance verified database integrity, no new foreign-key violations, unchanged
8 submitted applications, 573 shared company ratings and 228 surviving scores.
Results and validation are in `data/maintenance/liveness/2026-10-16-first-run.json`
and `2026-10-16-first-run-validation.json`; consistent pre-run SQLite backups are
under `data/backups/liveness-first-run-20261016T084211/`.

After the [Ponytail review](research/posting-liveness-ponytail-review-2026-10-16.md),
the installed Hermes entrypoint was manually run with revision `a5658d1a` on
2026-10-16. All 209 current candidates were checked: 165 active, 42 uncertain,
and 2 explicitly closed and deleted. The original 43 uncertain postings now have
13 active, 28 uncertain and 2 deleted (opportunities 154 and 354). Validation
confirmed all 43 persisted outcomes, database integrity, no dangling deleted-job
references or pending cleanup, and unchanged submitted applications/shared evidence.
Results, preflight source hashes and validation are retained under
`data/maintenance/liveness/2026-10-16-fixed-run/`; the consistent pre-run backups
are under `data/backups/liveness-fixed-run-20261016T101520/`. The cron remains
active on the same repository workdir and wrapper; doctor passed after the run.

Before future deployment changes, take consistent SQLite backups and verify the
installed script and timezone. Never delete based on old scan-report liveness
fields. Uncertain checks retry at the next scheduled run or via manual `--apply`;
they do not block other workflows, and no separate retry timer is installed.

Local cleanup on 2026-10-16 removed completed liveness experiment scripts,
temporary probes and duplicate progress outputs. Raw source captures, experiment
inputs/results, acceptance records and pre-deletion database backups remain.
The removed-file inventory and hashes are in
`data/maintenance/liveness/local-cleanup-20261016.json`.
