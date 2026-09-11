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

### Scoring Rules — attractiveness-v1 pilot

用户于 2026-09-11 确认：主分数表达入职吸引力（工作方向、待遇、团队、公司是否令人满意），能力竞争力单列。当前仅在独立试评中启用；试评放入 `reports/scoring-pilot-2026-09-11/`，不覆盖历史报告，不进入 pipeline/tracker，不沿用旧分数的申请阈值。正式流程迁移需在试点评审后决定；旧匹配分与吸引力分不可换算或混排。

本节是试评的评分与格式契约，覆盖试评中 `_shared.md`、`oferta.md`、batch 的整体判断、平均章节分和旧五维规则。正式旧报告仍属于原模型，不得标为 attractiveness-v1。

1. 冻结完整 JD、批准的候选来源和本规则，记录源路径与 SHA-256。历史报告只供审计，不能作为候选事实或完整 JD 的替代品。完整 JD 缺失则记录 incomplete，不生成评分报告；历史快照试评必须注明未复核当前有效性。
2. 权重只读取 `config/profile.yml` 的 `attractiveness.weights`。四维为 direction（实际工作内容与职业方向）、compensation（相对所在地个人底线和目标的薪酬福利）、team（工时、管理、协作、自主权、工作安排）、company（业务前景、稳定性、技术投入）。能力缺口、资格门槛和真实性独立展示；同一负面事实只在一个吸引力维度计分。公司名气本身不加分；公司资料不等于团队资料；明确远程是 team 的正面依据，现场办公不扣分。
3. 先定档再加权：1=明显不符合偏好；2=明显不足、需要较大妥协；3=达到可接受水平；4=明显诱人、符合期待；5=非常理想且有充分证据。分项仅取整数；普通后端在可接受方向内，不能仅因非 AI 岗打低分。薪酬刚达到个人最低线为3分，达到明确个人目标支持4分，5分需要显著超出目标的证据；没有具体目标时不能自行补造。薪酬区间上限、OTE、股权或公司支付能力不能冒充保证底薪。
4. 证据不足以判定整个维度时 score=null，计算范围[1,5]；有部分正面线索可写在理由中，但不能凭想象缩窄范围。已知维度为[score,score]。总下限/上限分别为四维下限/上限的加权和，保留两位小数以便复算；coverage 为已知维度权重之和（0–1）。范围不是统计置信区间，中点不是估计分数。全部未知也不能跳过完整 JD 前置条件。
5. 高吸引力且条件充分核实的岗位优先申请；高潜力但未知项多的岗位优先补证。不得仅按区间下限排序；不得把旧4.0/4.5匹配分阈值搬到吸引力范围上。既有 Stage 0 门槛不变；试评不宣称已通过实时门槛或直接触发申请。
6. 保持以下二级标题及顺序：`## Machine Summary`、`## A. 岗位概览`、`## B. 能力竞争力`、`## C. 入职吸引力`、`## D. 薪酬与需求`、`## E. CV 变更计划`、`## F. 面试与补证`、`## G. 岗位真实性`、`## Risk Summary`、`## Evaluation Checklist`。能力映射逐项列出 JD 的实质必备与加分要求，拆开复合要求，使用 Proven/Adjacent/Gap/Unverified，并列候选证据、招聘影响及应对；不得将原型、进行中或相邻经验提升为生产证明。Checklist 汇总地点、雇佣、规模、工时、待遇、真实性及未解决的能力问题。
7. Machine Summary 使用 `scoring_model: attractiveness-v1`、`scope: pilot`、`score: null`（不给旧消费者伪造单分）、`company`、`role`、`complete_jd: true`、`sources`、`dimensions`、`attractiveness`。sources 为 `{id, path, sha256}` 数组（路径相对仓库）；dimensions 的四个键各为 `{score, rationale, evidence: [{source, quote}]}`，引用须逐字来自冻结来源。未知项也须解释缺失信息；已知项必须有证据。attractiveness 为 `{lower, upper, coverage}`，只由确定性计算生成。报告正文必须使用相同范围，不展示一个旧式总分。
8. 交付前运行 `node scoring-report.mjs <报告路径>...`。必须通过标题顺序、完整 JD 声明、分项范围、权重、源哈希、引文及总分复算检查，再人工逐项审核证据是否支持判定、能力映射是否覆盖 JD。机械校验不能证明语义公允。重复盲评使用同一冻结材料，保留每次原始判定并报告差异，不能用重复计算代替重复评估。

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
