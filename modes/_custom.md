# Custom Instructions -- career-ops

<!-- ============================================================
     THIS FILE IS YOURS. It will NEVER be auto-updated.

     Put your own house rules, custom workflows, and automations
     here -- anything you want the agent to ALWAYS do (or never do).

     This is for PROCEDURAL rules ("HOW I want things done").
     For WHO you are (archetypes, narrative, comp, negotiation),
     use modes/_profile.md instead. Keeping the two separate keeps
     each one readable.

     The agent reads this file alongside the system instructions;
     your rules here take precedence over the defaults, as long as
     they don't break the Data Contract (your files are never
     touched, and we never auto-submit an application for you).

     Because this is a user-layer file, anything you write here
     survives `node update-system.mjs`. Put customizations HERE,
     not in CLAUDE.md / modes/_shared.md / other system files --
     those get overwritten on update.
     ============================================================ -->

## House Rules

<!-- Rules the agent should always follow. Examples:
     - Always write evaluation summaries in British English.
     - Never include a photo in my CV (US / ATS-first market).
     - Cap each batch run at 20 listings unless I say otherwise.
     - If a report scores below 6, skip the cover letter. -->

(none yet -- add yours above)

## Custom Workflows

<!-- Multi-step routines you run often, given a short name. Examples:
     - "weekly review": scan my saved portals, evaluate the new roles,
       then give me a one-paragraph summary of the top 3.
     - "prep <company>": pull the JD, generate STAR stories from
       article-digest.md, and draft 5 likely interview questions. -->

- For every scan, run enabled `search_queries` with `method: playwright_listing` before WebSearch. Use `browser-extract.mjs` against the configured live LinkedIn Jobs URLs, keep only `/jobs/view/` links, canonicalize and deduplicate across cities. Fall back to the Playwright MCP on the same URL if the CLI extractor fails; never silently treat browser failure as zero LinkedIn results.
- Keep LinkedIn mainland China and Hong Kong discovery as separate searches. Public search-engine `site:linkedin.com` queries are fallback-only because their index under-represents mainland listings.

## Pipeline Rules

Pipeline is a two-stage review workflow. Never generate a CV, PDF, cover letter,
application answer, or tracker addition during Stage 1.

### Stage 0 — Canonical terminal pre-screen

Stage 0 is implemented once in `lib/prescreen-core.mjs` and is shared by scan, pipeline, and batch. Each caller must build the documented evidence input and run or reuse a schema-valid cache result via `prescreen.mjs`; it must not maintain a separate business-rule gate.

- `fail`: explicit hard failure only—location, company size, employment, compensation, terminal experience gap, two or more core mandatory capability gaps, or an absent mandatory credential. Write `Processed` plus `data/discard.log`; do not reserve a report number.
- `pass`: no hard failure and all required evidence is complete; proceed to Stage 1.
- `uncertain`: unknown gate, adjacent/unverified capability, or borderline experience; proceed to Stage 1 with exact questions carried into the checklist. Unknown is not fail.
- `incomplete`: missing full JD or required assessment fields; keep Pending and complete the evidence before Stage 1.

Scan normally writes an `incomplete` cache placeholder because listing metadata is not a candidate-evidence-backed assessment. Pipeline and batch reuse valid hash-matching results and rerun only stale, missing, invalid, or incomplete results. Liveness remains a separate check.

### Stage 0 — Terminal pre-screen

Use `lib/prescreen-core.mjs` as the sole rule engine and `node prescreen.mjs --input {evidence.json} --cache-dir data/prescreen-cache` as the persistence boundary. Scan records `incomplete`; pipeline and batch reuse hash-valid results and rerun only stale, missing, invalid, or incomplete records. Keep liveness separate.

Extract the complete JD before scoring or reserving a report number. Apply the
pre-screen after liveness verification and before the full evaluation. A role
reaches Stage 1 only when it has no explicit hard failure.

Mark the role `skipped (pre-screen mismatch: {reason})` in Processed and append
the same reason to `data/discard.log` when any of these is true:

- An explicit company gate fails: location, minimum company size, accepted
  employee/contract classification, applicable work authorization, or disclosed
  compensation after the WLB adjustment.
- The JD states a minimum number of years and the candidate's verified relevant
  experience is at least three years below that minimum. Smaller gaps are
  borderline rather than terminal; for example, `4 years required` versus
  `3+ years verified` survives, while `10 years required` versus `3+ years
  verified` does not.
- Two or more capabilities that the JD presents as core mandatory work are
  `Gap`, or one indispensable licence, credential, or domain requirement is
  explicitly mandatory and absent. Preferred, bonus, or nice-to-have items do
  not count.

An `Unknown` is not a failure. Resolve it with bounded research when possible;
if only the recruiter can answer it and the candidate otherwise passes, carry
the exact question into Stage 1. Topic similarity or a strong adjacent skill
does not offset an explicit hard failure. A discarded role gets no report,
score, report number, application artifact, or human-confirmation slot unless
the user explicitly asks to override that specific discard.

### Stage 1 — Evaluate and wait for confirmation

1. Generate an evaluation report only for roles that survive Stage 0. Confirmed
   duplicates, expired postings, and terminal pre-screen mismatches skip the
   full evaluation.
   If an interrupted run already created a report for the same URL, reuse that
   report number and finish its checklist instead of reserving a duplicate.
2. Every report must end with a `## Confirmation Checklist` containing:
   - Company gates: location, legal employer and employment type, company size,
     five-day workweek/WLB, compensation, and posting legitimacy. Mark each
     `Pass`, `Fail`, or `Unknown`, cite the evidence, and name what must be
     confirmed.
   - Capability match: every material JD requirement mapped to exact evidence
     from the approved candidate sources. Mark each `Proven`, `Adjacent`,
     `Gap`, or `Unverified`; state its hiring impact and the proposed response.
   - CV change plan: proposed headline/summary emphasis, bullets to select or
     move earlier, evidence-backed rewrites, bullets to omit, and gaps that must
     not be claimed.
   - Decision choices: `Proceed`, `Reject`, or `Provide more evidence`.
3. Move evaluated roles out of Pending into an `## Awaiting Confirmation`
   section using `- [~] #NNN | URL | Company | Role | Score/5 | Report: path`.
   Do not mark them Processed yet.
4. Maintain one consolidated `reports/pipeline-review-{YYYY-MM-DD}.md` table
   listing report number, company, role, score, company-gate result, material
   gaps, recommendation, and report link.
5. Before asking for a per-role decision, perform a fresh targeted investigation
   of every material `Unknown` or caution that could change the decision. Check
   current posting status, first-party requisition, legal employer and employment
   type, work location, five-day workweek/WLB, compensation, work authorization,
   team/role scope, and the candidate's material capability gaps. Use public
   evidence where available; do not merely repeat the Stage 1 summary. Present a
   decision brief with verified facts, unresolved recruiter questions, downside,
   upside, and a reasoned recommendation before offering `Proceed`, `Reject`, or
   `Provide more evidence`. Human confirmation is for preferences, non-hard
   capability gaps, and recruiter-only unknowns—not for roles that already fail
   Stage 0. An unresolved item may remain `Unknown` only after bounded targeted
   research and must name the exact question to ask.
6. After all Stage 1 evaluations, show that table and stop. Wait for the user's
   explicit per-role decisions before any Stage 2 work.

Existing reports or PDFs created before this workflow are not implicitly
approved. If they lack a completed Confirmation Checklist and an explicit user
decision, backfill the checklist, include them in the consolidated review, and
treat their CV/PDF artifacts as provisional rather than application-ready.
Before surfacing any existing Awaiting Confirmation role, reapply Stage 0 using
the complete JD and current candidate evidence. Move a terminal mismatch to
Processed and `data/discard.log` without asking for human confirmation; only
survivors are backfilled into the review. Re-extract the JD when no snapshot
exists.

### Stage 1 parallel orchestration

Keep `/career-ops pipeline` as the only user-facing entry point. Internally run
Stage 1 in waves of up to three jobs, matching the available worker-agent slots.

1. The coordinator snapshots and hashes the approved candidate sources once per
   run, reads every recognized Pending-like section, canonicalizes URLs/job IDs
   across sections, and selects the next three unique jobs in first-seen order.
   Duplicate rows become one evaluation packet; their useful annotations are
   merged, and the coordinator removes or moves every duplicate row together at
   commit. Report the duplicate count instead of silently processing one
   section. Then obtain immutable JD/company evidence. Isolated CLI/static
   extraction may run in parallel; any shared Playwright MCP fallback is queued
   and executed one at a time by the coordinator.
2. Dispatch one job per worker agent. Workers receive only the immutable job
   evidence and candidate snapshot. They may research and evaluate their own job
   but must not spawn agents, invoke skills, reserve report numbers, or write
   `reports/`, `data/pipeline.md`, `output/`, tracker files, or application
   artifacts.
3. Each worker returns one structured evaluation packet containing report
   Markdown, company gates, capability mapping, material gaps, recommendation,
   CV change plan, source citations, and the canonical URL. A worker may persist
   only its own interruption-safe staging packet under
   `data/pipeline-runs/{run-id}/{job-key}/`.
4. The coordinator validates every packet against the source snapshot. Missing
   checklist fields, unsupported candidate claims, URL mismatches, or malformed
   scores are worker failures and are never published.
5. After the wave finishes, sort valid packets by original pipeline order. Reuse
   an existing report number for an exact URL; otherwise reserve all required
   report numbers in one coordinator call. The coordinator alone writes reports,
   moves rows to Awaiting Confirmation, and deterministically rebuilds the daily
   consolidated review.
6. One worker failure never blocks successful siblings. Retry it once on another
   worker; after that keep it Pending with `needs attention` and continue.
7. Checkpoint after every wave and report progress at least every 60 seconds.
   Reruns resume by canonical URL and completed Confirmation Checklist, never by
   worker completion order, so interruption cannot duplicate reports.

The expensive evaluation work is parallel; shared-state publication remains
single-writer and serial. Stage 1 still stops after the consolidated review and
never starts Stage 2 without explicit per-role decisions.

When an unverified quantified or scope claim appears, offer four outcomes:
confirm it, correct it, mark it narrative-only, or `I don't know`. Never turn a
guess into a verified fact.

### Stage 2 — Only after explicit confirmation

- `Reject`: move the role to Processed with `rejected after review`; generate
  no application artifacts.
- `Provide more evidence`: leave it Awaiting Confirmation and update approved
  source files only after the user explicitly confirms the new facts.
- `Proceed`: use the confirmed checklist and CV change plan to generate the
  role-specific CV/PDF, then create tracker/application artifacts and move the
  role to Processed.

For `Proceed`, write the single-role `preparation/plan.json`, then use a drafter-reviewer handoff. The drafter may create the role-specific Reactive Resume payload, PDF, and application answers; it must not mutate `cv.md` or the configured Reactive Resume mother resume. A separate reviewer writes `review/application-review.json` using the validated `approve|revise|blocked` contract in `application-artifacts.mjs`. Required fixes go to `review/change-plan.json`; apply them and rerun validation before presenting an application as ready. Never submit.

Before rendering a role-specific CV, write its actual changes to the application
bundle's `cv/tailored/vNNN/changes.md`. The experience section must reflect the
JD through evidence-backed selection, ordering, omission, or rewriting; changing
only the summary and competency keywords is not a tailored CV. If no material,
truthful experience change is possible, say that the base CV is already the best
available version and ask whether to use it unchanged. Never label an unchanged
CV as tailored.

## Output Preferences

<!-- How you like results formatted. Examples:
     - Reports: lead with the score and the one-line verdict.
     - Show the per-step token breakdown after a batch run.
     - Save PDFs date-first: YYYY-MM-DD-company.pdf -->

(none yet -- add yours above)

## Off-Limits

<!-- Things the agent must never do for you. Examples:
     - Never auto-fill or submit an application without showing me first.
     - Never edit a system file to customize my setup -- put it here. -->

(none yet -- add yours above)
