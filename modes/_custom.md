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

### Scoring Rules — attractiveness-v1

2026-09-11 正式启用：主分数表达入职吸引力（工作方向、待遇、团队、公司是否令人满意），能力竞争力单列。所有新评估与重评写入 reports/{报告号}-{公司}-{日期}.md，并经校验和复核进入 Scored。旧报告保留原始记录，显示为待重评；旧匹配分与吸引力分不可换算或混排。

本节是正式评分与格式契约，覆盖 `_shared.md`、`oferta.md`、batch 的整体判断、平均章节分和旧五维规则。历史报告仍属于原模型，不得标为 attractiveness-v1。

1. 冻结完整 JD、批准的候选来源和本规则，记录源路径与 SHA-256。历史报告只供审计，不能作为候选事实或完整 JD 的替代品。完整 JD 缺失则记录 incomplete，不生成评分报告；历史快照评估必须注明未复核当前有效性。
2. 权重只读取 `config/profile.yml` 的 `attractiveness.weights`。四维为 direction（实际工作内容与职业方向）、compensation（相对所在地个人底线和目标的薪酬福利）、team（工时、管理、协作、自主权、工作安排）、company（业务前景、稳定性、技术投入）。能力缺口、资格门槛和真实性独立展示；同一负面事实只在一个吸引力维度计分。公司名气本身不加分；公司资料不等于团队资料；明确远程是 team 的正面依据，现场办公不扣分。
3. 先定档再加权：1=明显不符合偏好；2=明显不足、需要较大妥协；3=达到可接受水平；4=明显诱人、符合期待；5=非常理想且有充分证据。分项仅取整数；普通后端在可接受方向内，不能仅因非 AI 岗打低分。薪酬刚达到个人最低线为3分，达到明确个人目标支持4分，5分需要显著超出目标的证据；没有具体目标时不能自行补造。薪酬区间上限、OTE、股权或公司支付能力不能冒充保证底薪。
   direction 定档边界：5=JD 明确以首选 Agent/Applied AI 产品系统为主要工作，并明确承担从设计到交付或运营的职责；4=明确符合全栈/后端/AI 工程方向且有具体产品贡献，但首选 AI 产品职责并非主要工作或未明确；3=可接受的软件岗位，缺乏上述方向增益；2=明显偏离但仍有可迁移内容；1=主要工作不在可接受方向内。未声明行业偏好不扣分，也不阻止5分；候选人技能或年限不足单列竞争力，不改变工作内容本身的吸引力。team 评价实际管理与工作安排，不重复给 direction 的产品职责加分。
4. 证据不足以判定整个维度时 score=null，计算范围[1,5]；有部分正面线索可写在理由中，但不能凭想象缩窄范围。已知维度为[score,score]。总下限/上限分别为四维下限/上限的加权和，保留两位小数以便复算；coverage 为已知维度权重之和（0–1）。范围不是统计置信区间，中点不是估计分数。全部未知也不能跳过完整 JD 前置条件。
5. 高吸引力且条件充分核实的岗位优先申请；高潜力但未知项多的岗位优先补证。不得仅按区间下限排序；不得把旧4.0/4.5匹配分阈值搬到吸引力范围上。既有 Stage 0 门槛不变；评分完成不等于门槛通过；申请始终由用户选择启动。
6. 保持以下二级标题及顺序：`## Machine Summary`、`## A. 岗位概览`、`## B. 能力竞争力`、`## C. 入职吸引力`、`## D. 薪酬与需求`、`## E. CV 变更计划`、`## F. 面试与补证`、`## G. 岗位真实性`、`## Risk Summary`、`## Evaluation Checklist`。能力映射逐项列出 JD 的实质必备与加分要求，拆开复合要求，使用 Proven/Adjacent/Gap/Unverified，并列候选证据、招聘影响及应对；不得将原型、进行中或相邻经验提升为生产证明。Checklist 汇总地点、雇佣、规模、工时、待遇、真实性及未解决的能力问题。
7. Machine Summary 使用 `scoring_model: attractiveness-v1`、`score: null`、`company`、`role`、`complete_jd: true`、`jd_source`（冻结 JD 的 source id）、`sources`、`dimensions`、`attractiveness`。sources 为 `{id, path, sha256}` 数组（路径相对仓库）；dimensions 的四个键各为 `{score, rationale, evidence: [{source, quote}]}`，引用须逐字来自冻结来源。未知项也须解释缺失信息；已知项必须有证据。attractiveness 为 `{lower, upper, coverage}`，只由确定性计算生成。报告正文必须使用相同范围，不展示一个旧式总分。
8. 交付前运行 `node scoring-report.mjs <报告路径>...`。必须通过标题顺序、完整 JD 声明、分项范围、权重、源哈希、引文及总分复算检查，再人工逐项审核证据是否支持判定、能力映射是否覆盖 JD。机械校验不能证明语义公允。重复盲评使用同一冻结材料，保留每次原始判定并报告差异，不能用重复计算代替重复评估。

### Review and decision gate

- `scoring-report.mjs` 的命令行交付检查同时读取 `<报告路径>.review.json`。独立复核者提供 reviewer、report_sha256、verdict=approve，以及 checks 中 jd_complete/source_grounding/dimension_support/capability_coverage/no_double_count/gate_evidence 各自的 `{status: pass, finding}`。复核须解释引文如何支持档位、是否遗漏必备能力；不能仅核对字面存在。哈希绑定整份报告，修改后重新复核。复核记录是责任记录，不是数字签名，也不保证评估者永不出错。
- 复核还提供 gates（location/employment/size/compensation/eligibility/liveness，每项 Pass/Fail/Unknown）及 ready（boolean，表示工时等申请前必要条件已充分核实）。历史快照的 liveness=Unknown、ready=false。不能把信息未知写成条件失败。
- 正式决策读取 profile 的 `attractiveness.acceptable_line`，这是吸引力可接受线，不是旧匹配分阈值。任意硬门槛Fail→discard；否则上限低于线→deprioritize；否则门槛有Unknown、申请条件未核实或下限低于线→verify；其余→apply。等于线视为达到。完整JD缺失不产生评分，不进入该评分队列。
- Agent 可基于多个独立、同向且无可信反向证据的强信号进行事实推理并定档，不必机械等待单一来源直接给出结论。必须在复核记录中写明事实、适用范围、推理链、置信度与反向证据检查；品牌页自填、搜索摘要或市场数据单独不足以判定硬门槛，但与注册时间、官网业务阶段、JD 明示阶段等独立信号一致时，可支持 `Fail` 或 `Pass`。无法排除关键反向解释时仍用 `Unknown`。
- `node scoring-decisions.mjs` 只读读取 data/pipeline.md 的 Scored，重新验证报告与复核，生成 decisions、needs_review 和 invalid。shortlist、日报和申请选择统一使用此结果；invalid 不得进入推荐池。新评估发布前也可用显式 queue.json 验证，gate/readiness 必须与报告复核一致。deadline为已知ISO日期或null，effort_days为有依据的补证/准备预计工作日或null；无证据不填数。
- 先分apply/verify/deprioritize/discard；组内按已知截止日期较早、预计工作量较少、证据覆盖较高排列；仅apply组再按下限降序，其余以id稳定打破平局。缺失日期或工作量排在该字段已知项后。此顺序是透明的行动调度，不是假定未知机会不值得去；重叠区间不声称存在满意度的严格排序。
- 补充定档锚点用于定档校准：compensation的1/2分别是明显/轻微低于个人底线（均不能补偿硬门槛），3达到底线但未达目标，4达到明确目标，5有显著超出目标上沿的保证收入证据；无法区分相邻档时记录分歧，不能随意加小数。
- team：1有明确长期强制无补偿加班和差管理证据；2有明确需要较大妥协的工作安排；3同团队证据确认可接受工时、协作和管理；4在3基础上有明确弹性/自主权等正面实践；5在4基础上有实际远程选择、稳定可持续安排和团队证据支持。公司级福利宣传、hybrid单词或导师承诺不足以判定整个维度，保留Unknown。
- company：1有经营中断/资金无法持续的可靠证据；2有持续经营但明显收缩或资源不足证据；3业务持续、资源足以支撑岗位；4有可验证增长与持续技术投入；5在4基础上有强业务韧性与岗位所在业务的长期资源承诺。公司名气、单一增长数字不能独立确定整个维度；缺经营/团队业务投入关键证据时Unknown。
- 校准分别记录合成场景测试与真实证据测试。合成场景只能检验规则能否一致执行，不能证明真实招聘信息充分或实际满意度。新样本留出评估不能先给评估者参考答案；保留分歧，未校准边界列为上线前限制。

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

### Scoring Rules — 正式联网研究（research-required-v1）

状态：2026-09-11 用户批准正式启用并试运行。所有新建或主动重评的岗位报告必须执行本节，包括 evaluate/oferta、auto-pipeline、pipeline Stage 1 与 batch；定时任务进入这些评估流程时同样适用。只扫描、只展示已有 shortlist 和历史报告不触发重评。统一使用上述 attractiveness-v1 区间评分与行动规则。

本节覆盖 oferta 中“JD 未披露工资就压缩 D 并跳过研究/提问”的规则。沿用每岗位最多 5 次搜索、主评估者单轮研究；批量执行时把本节随 `_custom.md` 传给每个评分者。

- 打分前主动搜索待遇、团队和公司三维，不能因为 JD 没写就停止。先识别品牌、法律实体、招聘代理与实际雇主，再按公司+城市+职级查薪酬，按团队+地点查工时/管理/远程实践，按实际业务查经营、资金与技术投入。优先官方招聘、财报/公告、薪酬机构原始数据；员工反馈注明日期、地区、团队与自述性质，多个转载不算独立印证。预留至少一次查询给每个维度，可共用查询；访问失败记录失败，不能当作无风险或零结果。
- 综合评估允许外部证据支持分项，不要求全部来自 JD 或 offer。需要写清“事实→适用范围→推断→档位”：同公司同城同职级工资可帮助判断，但市场工资不能冒充岗位工资，保证底薪门槛仍需可对应本岗位的证据；公司级文化只能作线索，同团队的可核查实践可支持 team；财报、经营和投入证据可支持 company。过时、矛盾或身份不匹配的证据单列，无法定档才保留 Unknown。没搜到负面不是正面证据；没有薪资报价也不删除市场分析。
- 冻结短摘录及研究日志，不复制整页。新报告 sources 必须含 research（JSON）和本版 rules，校验器由规则标记强制检查研究记录；历史报告保留原版本，重评时必须采用当前规则。JSON含 searched_at、实际 queries（最多5条）、dimensions 的 compensation/team/company（queries为查询下标，conclusion、next_step），findings含唯一id、url、entity、scope（role/team/company/adjacent_role/market/unresolved）、status（retrieved/search_only/failed/excluded）、published_at（未知null）、limitation，以及 retrieved 才有的 source/quote（其他状态均null）。来源文件继续通过 SHA-256 校验。
- C 的理由纳入研究结论；D 保留 JD 报价与市场基准的区别；F 写剩余问题；Checklist 更新门槛证据。搜索结果摘要不能作为已读取正文；其他职位的远程政策不能直接转移；匿名客户不能借代理的工资/人数/口碑评分。独立语义复核须核对来源实体、时间、地区/职级/团队适用性及冲突处理，不能只验证引文存在。浏览器有效性核验仍单独执行。
- 正式报告交付条件：在 F 中保留“外部研究记录”，列出研究日期、实际查询，以及待遇/团队/公司各自的来源链接、短摘录、来源日期（未知写未知）、适用范围、结论和下一步；来源摘录随报告冻结保存。Evaluation Checklist 增加“联网研究：完成/受阻”及记录链接。三维均执行查询并说明结论才算完成；没有结果可算搜索完成，但不能把未知项判为通过。搜索工具不可用时标受阻，报告作为待完善草稿，保留原队列状态，不能宣称完整评分已完成。正常搜索后仍缺岗位资料则保留 Unknown 和补证问题，可按既有流程交付。
- 发布前运行 `node scoring-report.mjs <报告路径>`，再运行行动决策。复核缺失、过期或未通过则留在 Pending/待完善，不发布 Scored。Score 单元格统一为 `吸引力 L–U/5（覆盖率P%）`，行动以复核和当前 profile 重算；不再使用单分平均或4.0/4.5阈值。Stage 2 的 tracker 同样保留范围，不生成替代单分。

### Scored 发布与重评

- pipeline/auto-pipeline/batch 在报告及相邻 .review.json 校验通过后才把岗位移入 Scored；保留 URL、城市、报告号和报告链接。apply 表示建议用户启动申请准备，verify 表示优先补证，deprioritize 表示暂缓，discard 表示已核实硬门槛失败。它们不是投递状态，也不自动提交。
- 评分任务先处理 Pending，再按现有顺序重评 Scored 中 needs_review 的历史报告；每次合计最多30条，重新取得完整JD并核验有效性。新版本通过前保留旧报告和原条目；更新时使用新日期报告与新复核记录。禁止把旧数值按比例变成新分数。
- shortlist/日报直接读取 `node scoring-decisions.mjs`：按行动分组展示范围、覆盖率和缺失信息；needs_review 单列旧报告待重评，invalid 单列校验失败。仅展示不触发搜索或重评。统计分开计算旧匹配分与新吸引力；能力差距分析不使用吸引力作为技能权重。
