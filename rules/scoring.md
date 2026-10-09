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

The user-facing flow is discovery → scan → score → action decision → selected-role
application preparation. `workflow.career_ops` owns task identity, business
transitions, and the JSON CLI; Hermes only schedules the scan and score scripts.
Node providers and guarded browser readers may collect evidence, but Python
makes the filtering, prescreen, score, action, and publication decisions.
`data/opportunities.db` is the business source of truth. LangGraph checkpoints
record progress and never replace committed business facts.

### Prescreen and JD handoff

LangGraph scan freezes the source capture, extracts the complete JD, and calls
`workflow.prescreen.evaluate` for deterministic Stage 0 decisions. Liveness is
checked separately. A verified hard mismatch produces an exclusion with its
reason and evidence; it does not produce a score or application package.
Incomplete core evidence waits for a new capture. Unknown nonterminal facts
remain Unknown and follow the JD report into the score checklist. A completed
scan JD report is the normal score input; a changed JD or candidate/rule input
requires explicit re-evaluation. A cache is reusable only when its content and
input fingerprints still match.

### Score and action queue

LangGraph scoring uses the four-dimension policy in `rules/evaluation/four-dimension.md`.
Three parallel company/culture/compensation main Agents research public facts through one
fixed retrieval tool and stateless document summaries, without cumulative token or score-stage time caps. Each main Agent organizes
facts directly for its own Jev request as soon as ready; valid exact company scopes
reuse persistent evidence and ratings. Job direction is scored separately.
Current JD, candidate and policy inputs bind each report version. Invalid or absent
summaries and failed ratings remain pending; other dimensions retain their results.
Sources and raw model products are retained for review, without exact quotation or
hash-integrity acceptance of factual summaries.

`scores` displays raw dimension scores, confidence, independent sufficiency and input
validity. Initial `decisions` uses scores only: all four dimensions must be present
and at least 4 for `focus`; otherwise `deprioritize`. Confidence and sufficiency
are informational, not recommendation gates. Confirmed hard failures remain exclusions. Historical three-dimension reports
retain their original form and become stale through policy fingerprints. Applying
remains an explicit user choice.

### Selected-role application preparation

LangGraph apply prepares the selected role's plan, materials, Reactive Resume
payload, and PDF, then waits for whole-package human review and confirmation.
It never mutates `cv.md` or the configured Reactive Resume mother resume and
never submits an application or sends an application message. An unchosen
scored role remains available.

Before rendering a role-specific CV, record its actual changes in the
application bundle's `cv/tailored/vNNN/changes.md`. Tailoring must make
truthful, evidence-backed choices in the experience section, not only change
the summary or keywords. If no material experience change is justified, state
that the base CV is the best available version and ask whether to use it
unchanged. Never label an unchanged CV as tailored. When a quantified or scope
claim lacks verification, offer to confirm, correct, mark narrative-only, or
record “I don't know”; never promote a guess to a verified fact.

## Output Preferences

### Scoring Rules — attractiveness-v4

唯一四维标准为 `rules/evaluation/four-dimension.md`：direction、company、culture、compensation 独立小数期望分（1–5）、原始 confidence 和独立 evidence_sufficiency；无总分、权重或覆盖率。缺失评分保留 null/pending。公司事实按实体与精确适用范围维护，未知职级或城市不猜定。

报告保持 A/B/C/D/E/G、Risk Summary、Evaluation Checklist、Machine Summary 的原顺序。正文由模型提供，能力竞争力、门槛和真实性单列。Machine Summary 使用 scoring-v3、attractiveness-v4，保留 sources/advertised_comp，保存 dimensions、company_profiles、company_research 和按四维分数计算的 recommendation。初期四维均有分数且各自≥4才推荐；confidence与充分性仅作提示，不设置准入阈值；原始分数不截断取整，阅读显示保留两位小数。摘要按结构与适用范围接收，来源及原始响应留存供审阅，不要求逐字引文匹配或摘要 hash 完整性门禁。不得改写历史报告或从旧总分换算四维。

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

### 正式公司研究与发布

正式调研由一次 Codex CLI 任务完成公司的三个维度，使用 gpt-6-astra / medium 与实时搜索，最长 15 分钟。只接收公开公司资料和公开 JD，不发送候选经历、CV 或私人薪资偏好；私人标准仅用于授权 Jev 评分。直接返回带来源 URL 的事实数组，无自研采集／逐篇摘要循环。保留提示词、原始输出、工具日志与用量；引用和日志不等于完整网页正文。失败保留记录，不切换模型。

有效公司 scope 与研究规则匹配时复用，新增 scope 只补缺失范围；研究规则变更或过期重查，评分规则变更只重新评分。SQLite 保存四维原始值与评估产物，旧结果保留。发布检查当前输入、结构、数值范围及报告身份。公开资料的岗位适用性未完全确认也可作为有边界的参考；推荐仅按四维分数，充分性展示但不设门槛。

### Hermes 定时评分

- 固定 score cron 每二十分钟触发一次，`scripts/career-ops-score.sh` 调用 Python `system advance` 推进一个持久任务，再调用 `system notify cron`。每次 Codex 调研最长 15 分钟，其他单次请求仍有超时；持久任务与公司锁防止重复研究，调度间隔不能代替互斥。
- `data/opportunities.db` 是机会与任务的权威队列；任务行记录尝试次数、模型调用与耗时。首次失败排在未尝试岗位后，第二次失败留待人工处理，不再自动重试。手动处理或候选资料/规则更新后可重评。
- scan 在筛选、去重后保留来源抓取证据；失败保留原因，不能写 complete_jd=true。score 使用 scan 正式交接的完整 JD 和来源有效性证据；历史快照不代表岗位此刻仍开放，申请前重新核验。
- 任务锁防止同一岗位并发执行；SQLite 短事务维护业务归属，网络和模型调用不占用业务事务。
- 初始上下文由程序组装：当前评分规则、候选主来源、本岗位 JD 与冻结研究。定时任务不预载全功能 skill、上轮自然语言输出或全池报告。
- 预筛中明确未知的相关年限保留待确认并继续评分；不能把“尚未证明满足年限”写成零年并淘汰。
- 模型提供事实和判断；Python/LangGraph 负责来源冻结、结构化校验、哈希、报告及业务发布。同一输入仅发布一次；证据或报告不合格则修订或等待，不越过确定性门禁。
- 三维公司 agent 各自保存采集及摘要原始产物与资源记录；正文保留 provider 实际完整返回，查询/读取按证据缺口进行，网络调用受每维独立 credits 限制，重复及访问失败记录停止原因。有效公司范围复用，无需按岗位重复研究。
- 检查点绑定输入和产物哈希；候选事实、评分规则或 JD 变化使受影响阶段失效。来源有效性不足则等待补证；每岗通过确定性校验后立即发布，历史报告保留原格式和原始证据。
- 单次发布率、超时率、尝试次数和累计耗时分别记录；恢复运行的耗时不得称为从头完成的耗时。CV详细改写和面试准备在用户选岗后执行。

三维并行，分别完成和评分。制度不存在必须有明确来源支持，未查到不能推出不存在；纯粹“无证据显示”等否定不进入事实，缺口仅写为具体后续问题。
