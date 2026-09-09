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

## Workflow Authority

The user-facing workflow has exactly two top-level modules:

1. **A — 机会搜寻与评估 (Opportunity Discovery & Evaluation):** Discover/scan → Verify/Liveness → Pre-screen/Stage 0 → Evaluate/Stage 1 → Shortlist/Scored.
2. **B — 申请准备与投递 (Application Preparation & Submission):** Select → Prepare/Preparation Plan → Tailor/Reactive Resume → Review/Drafter-Reviewer → Verify/PDF-ATS → Submit (user only).

`scan`, `pipeline`, Stage 0, Stage 1, and Stage 2 remain internal compatibility
terms. `pipeline` is the internal orchestrator; `data/pipeline.md` is the
opportunity inbox/database. Stage 1 never generates a CV, PDF, cover letter,
application answer, or tracker addition. It ends at Scored. The user selects a
specific scored role and manually starts Stage 2. Nothing submits automatically.

### Stage 0 — 统一预筛选

执行前阅读 [预筛选契约](../docs/PRESCREEN.md) 和 [pipeline 流程](pipeline.md#canonical-stage-0-pre-screen)。规则只由 `lib/prescreen-core.mjs` 实现，证据输入与缓存通过 `prescreen.mjs` 处理；liveness 单独检查。

- `fail`：移至 Processed，向 `data/discard.log` 追加原因，不分配报告号、不生成评分或申请材料；只有用户明确覆盖该岗位的淘汰决定才重新处理。
- `pass`：进入 Stage 1。
- `uncertain`：进入 Stage 1，并将确切问题带入 Evaluation Checklist；未知不等于失败。
- `incomplete`：保留 Pending，补齐完整 JD 与所需证据后再评估。

扫描仅写 `incomplete` 占位；pipeline/batch 复用合法且哈希匹配的完整缓存，仅重跑缺失、过期、无效或 `incomplete` 记录。

### Stage 1 — Evaluate and produce a scored list

1. Generate an evaluation report only for roles that survive Stage 0. Confirmed
   duplicates, expired postings, and terminal pre-screen mismatches skip the
   full evaluation.
   If an interrupted run already created a report for the same URL, reuse that
   report number and finish its checklist instead of reserving a duplicate.
2. Every report must end with an `## Evaluation Checklist` containing:
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
3. Move evaluated roles out of Pending into the `## Scored（已评分 · 可手动启动申请）`
   section using `- [~] #NNN | URL | Company | Role | Score/5 | Report: path`.
   This is the automated scored-list state; it is NOT a per-role wait gate.
4. Maintain one consolidated `reports/pipeline-review-{YYYY-MM-DD}.md` table
   listing report number, company, role, score, company-gate result, material
   gaps, recommendation, and report link.
5. After all Stage 1 evaluations, output the scored list and STOP. The user
   manually starts Stage 2 for a selected scored role.

Existing reports or PDFs created before this workflow are not application-ready
by default. If they lack a completed Evaluation Checklist, backfill it and
include them in the consolidated review. Reapply Stage 0 using the complete JD
and current candidate evidence before moving any legacy `[~]` role to Scored.
Move a terminal mismatch to Processed and `data/discard.log`; re-extract the JD
when no snapshot exists.

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
   moves rows to Scored, and deterministically rebuilds the daily
   consolidated review.
6. One worker failure never blocks successful siblings. Retry it once on another
   worker; after that keep it Pending with `needs attention` and continue.
7. Checkpoint after every wave and report progress at least every 60 seconds.
   Reruns resume by canonical URL and completed Evaluation Checklist, never by
   worker completion order, so interruption cannot duplicate reports.

The expensive evaluation work is parallel; shared-state publication remains
single-writer and serial. Stage 1 ends with the consolidated scored list and
never starts Stage 2 automatically. The user manually triggers Stage 2 for a
chosen role.

When an unverified quantified or scope claim appears, offer four outcomes:
confirm it, correct it, mark it narrative-only, or `I don't know`. Never turn a
 guess into a verified fact.

### Stage 2 — User-triggered application only

Stage 2 starts only when the user invokes the application workflow for a
specific scored role. Selecting that role is the trigger; there is no per-role
queue or approval keyword.

- Generate the selected role's preparation plan and application artifacts using
  its scored report/checklist, then run the drafter-reviewer gate below.
- A scored role is never discarded merely because the user has not chosen it.
- No Stage 2 work is run by the daily scan/evaluation cron.

After manual selection, write the single-role `preparation/plan.json`, then use a drafter-reviewer handoff. The drafter may create the role-specific Reactive Resume payload, PDF, and application answers; it must not mutate `cv.md` or the configured Reactive Resume mother resume. A separate reviewer writes `review/application-review.json` using the validated `approve|revise|blocked` contract in `application-artifacts.mjs`. Required fixes go to `review/change-plan.json`; apply them and rerun validation before presenting an application as ready. Never submit.

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
