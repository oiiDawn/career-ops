# career-ops 最小实现与目录结构审查

实施状态：2026-09-11 已按确认范围在 worktree 移除 Web/TUI，见 [实施与验证记录](implementation-2026-09-11.md)。以下保留实施前审查快照。

初审日期：2026-09-10；场景修订：2026-09-11。对象：`/Users/oii/.codex/worktrees/948e/career-ops` 当前提交。只生成审查附件，没有修改或删除现有实现。

**目标已明确：Hermes Agent 是主要宿主，现有 cron 驱动机会发现与评估 A，用户选定岗位后执行申请准备 B；Web 与 Go TUI 明确退役。仓库负责领域规则、确定性工具与持久数据，Hermes 负责推理、调度与消息投递。不在仓库重建调度器或模型运行平台。**

本次只修正分析与清单；没有更改 Hermes、cron、业务规则或生产数据。

## 1. 覆盖范围与证据强度

- 清点全部 **1,193 个 Git 路径**，读取 1,179 个文本文件，共 **246,041 行**；另有 14 个二进制资源。文本行数包含代码、注释、文档、测试、锁文件和夹具，不能等同于业务代码行数。
- 文件内容合计 42,032,714 字节；不含 `.git` 元数据。本次初始检查没有未跟踪或 ignored 文件，也没有用户未提交改动。审查附件不计入基线。
- [逐文件清单](file-inventory.md) 为每个路径提供职责、建议、引用候选数及源头摘录；[机器可读清单](file-inventory.json) 另含 SHA-256、导入与导出声明、引用候选列表。
- 全量清单是**全文读取后的静态提取与分类**；人工语义复核集中在入口、动态加载、A/B 流程、渲染与事实校验、状态写入、Web/CLI 边界、测试和更新器。不是 246,041 行逐行正确性审查，也没有为每个文件证明运行时可达性。
- 引用统计来自文件名文本匹配，包含文档和测试，可能同名误匹配；目录加载、框架约定、拼接路径和外部调用会漏检。**引用为零不构成删除证据。**
- 当前缺少 `cv.md`、`config/profile.yml`、`modes/_profile.md`、`portals.yml`。`doctor` 因缺少 `js-yaml` 未运行成功。因此不能判断个人实际启用的全部岗位源、模型、市场规则或模板。没有为审查启动 onboarding、复制其他目录的个人资料或安装依赖。
- 历史记忆只用于提醒「worktree 可能没有用户层」和「以本 fork 为准」；流程结论以当前 `modes/_custom.md` 为准。当前规则已经是 Stage 1 到 Scored，用户手动选择后进入 Stage 2，不沿用旧的逐岗位 Proceed 门槛。

## 当前 Hermes 场景：已读取实际配置

读取了本机 `/Users/oii/.hermes/cron/jobs.json` 中匹配 career-ops 的三个任务，以及两个已安装 skill 的相关说明。配置中的三个任务均 enabled，workdir 均为 **`/Users/oii/dev/career-ops`**，不是本次审查的 worktree。

| 现有任务 | 配置中的日内触发时间 | 职责与边界 |
|---|---|---|
| `career-ops scan（发现）` | 06:00、18:00 | 发现到 Pending；可写 incomplete 预筛占位；不评分、不生成日报，静默结束 |
| `career-ops score（评分）` | 00:00、03:00、09:00、12:00、15:00、21:00 | 每轮最多取 30 条 Pending，完整 JD → Stage 0 → Stage 1 → Scored；不做 scan，不生成申请材料，静默结束 |
| `career-ops report（日报）` | 08:30 | 只读汇总；由 Hermes 投递到 Discord；即使无变化也输出完整日报 |

以上是任务配置的时间表达，不额外假定调度器时区；未读取 Gateway 生效环境或核验每次实际运行。scan/score prompt 规定 120 分钟上限、约 110 分钟保存部分结果，属于任务要求，不构成硬超时已在运行环境生效的证明。

用户所称「AB cron」在当前配置中是 **A 的 scan/score/report 拆分**；三个任务及仓库规则都禁止自动进入 B。分析保留这一事实，不将每日 cron 扩大成自动申请。以后如需要定时执行 B，应另外明确岗位选择来源；本次没有这项行为变更。

抽查生产 checkout 与 worktree 的 `scan.mjs`、`modes/_custom.md`、`AGENTS.md`、`package.json`、`pipeline-lock.mjs`、`lib/prescreen-core.mjs`、日报模板，内容相同。这支持关键架构分析复用，**不代表全部 1,193 个文件或个人配置已比对**。

### 新发现：先收敛 Hermes 的重复流程说明

三个 cron 都同时加载 `career-ops` 和 `career-ops-workflow`。当前安装的 `career-ops-workflow/SKILL.md` 仍含「两 cron 尚未实施」、2400 秒和 Markdown 表格日报；其 `references/cron-scored-list.md` 也使用表格。`career-ops/SKILL.md` 已描述三个 cron，但日报段仍残留表格要求。实际 report job 与仓库 `docs/DAILY-REPORT-TEMPLATE.md` 要求 Discord 紧凑列表、禁止 Markdown 表格。

这是本场景最值得精简的说明层：**一个 Hermes skill 负责定位仓库并加载规则，仓库 `_custom.md` 定义 A/B，日报模板只保留一个权威来源，cron prompt 仅承载各任务范围、预算与投递要求。** 合并前保留两份 skill 中独有且仍适用的操作经验；先修改所有实际消费者，再退役重复入口。无需新造 Hermes 插件框架。

这些是后续清理建议，外部 skill 和定时任务本次均未修改；没有执行它们的任务指令。

## 2. 现有各层到底做什么

| 层 | 当前作用 | 最小实现判断 |
|---|---|---|
| 根目录 190 个路径 | CLI、领域辅助、测试、文档与配置混排 | 根目录确实拥挤，但先裁能力，再归位；不为整齐立即搬家 |
| `modes/` 169 个文件 | Agent 执行规则、多市场流程、个人流程覆盖 | 核心行为定义，不能一概视作文档冗余；流程与市场扩展应分清 |
| `providers/` 89 个文件 | ATS/招聘源适配和 HTTP、解析、注册辅助 | 有真实多实现消费者，保留适配边界；不能用「每文件一个导出」作为坏味道 |
| `lib/`、`utils/` | CLI 参数、预筛、缓存、内容处理与计费辅助 | 保留实际共享逻辑，按职责归位，避免新增万能 utils |
| `web/` 214 个文件 | Next/React 界面、HTTP 路由、Agent 执行、数据桥接与测试 | 明确退役：页面、HTTP 路由、Web 调度与专属测试一起移除 |
| `dashboard/` 45 个文件 | 独立 Go TUI、Markdown 解析、交互和测试 | 明确退役：不再维护 Go 运行时、TUI 和专属 CI |
| `batch/`、独立模型脚本 | Claude 批执行与 Gemini/OpenAI/Ollama/OpenRouter 执行路径 | Hermes 已承担调度与推理；独立执行器优先退役，但保留被间接调用的共享逻辑 |
| `plugins/`、registry 和 loader | 带凭据的外部集成、发现、权限和执行 | 未启用不等于无用；不用扩展生态时才整体删，保留时不可删权限约束 |
| `templates/`、`fonts/` | CV/信件布局与领域表格 | 保留现用模板、字体和状态契约；法律/市场表不是 CSS 模板，不能一起扫掉 |
| 根测试、`test/`、`tests/`、Web/Go 测试 | 不同测试历史和运行器 | 收敛运行机制，不按数量删除保护行为的测试 |
| `data/`、`reports/`、`output/` 等 | 用户持久数据与产物，当前多为空目录脚手架 | 永久保护；缓存和索引与原始事实分开处理 |
| `.github/`、scaffolder、宿主入口、翻译 README | CI、社区运营、发布与多 CLI 安装 | 个人 fork 可裁分发/运营面；不影响业务不代表不影响 CI/安装 |

## 3. 按收益排序的裁剪建议

以下行数是对应现有文件的完整文本行数，不是已验证可直接删除的净代码量。成组退役必须同步处理调用、配置、测试和当前文档。各组互不重叠；不把专属测试之外的共享测试算进收益。

| 标签 | 要裁掉的面 | 替代与前提 | 当前规模 |
|---|---|---|---:|
| `delete:` | `web/` 整套 Web 产品 | 用户已明确不需要；同时清理根测试/更新器中的 Web 引用和 `.github/workflows/web-ci.yml` | 214 文件 / 29,298 行 |
| `yagni:` | 非中英说明及非所需市场流程 | 保留英文核心、简体中文说明与实际市场规则；输出语言与市场规则不能混为一谈 | 候选 127 文件 / 21,908 行 |
| `delete:` | `dashboard/`、`build-dashboard.mjs` | 用户已明确不需要；清理 Go CI、构建命令与更新器重建逻辑 | 46 文件 / 11,822 行 |
| `yagni:` | 7 个独立模型/批量根脚本及 `batch/` | Hermes 执行 A/B；已读取的 cron 不直接调用这些执行器，仍需排查被加载 modes/skills 的间接调用 | 13 文件 / 5,351 行 |
| `yagni:` | bundled plugins、registry 与管理实现 | 确认没有启用集成后退役；原始 `providers/` 继续保留 | 37 文件 / 3,267 行 |
| `yagni:` | LaTeX 路径的 7 个核心文件 | 已确认只用 Reactive Resume/HTML 后退役 `.tex` 构建、编译、模式及模板 | 7 文件 / 1,111 行 |
| `delete:` | Web shader、主题和 UI 组件 | 随 Web 整体删除；不再花时间改成 CSS 或重构前端组件 | 已包含在 Web 收益中，不重复计数 |
| `shrink:` | `test-all.mjs` 和 `tests/helpers.mjs` 的自制执行机制 | 将断言迁到 `node:test` / `node:assert/strict`；构建、语法、数据契约检查保留独立命令 | 17,091 + 568 行是待整理面，**不是可整删收益** |
| `stdlib:` | `tracker.mjs:373` 局部 `flagValue` 与长期散落参数处理 | 近期复用 `lib/cli-flags.mjs`；统一运行时后按契约迁到 `node:util.parseArgs` | 不夸大行数；重复 flag、负数和缺值语义需核对 |
| `shrink:` | `batch/batch-runner.sh` 的 `SKIP_PDF` 与 `--skip-pdf` | Stage 1 已不生成 PDF，该参数只留下提示；无外部消费者后删变量、解析、说明及提示分支 | 兼容 CLI 的退役决定，不能静默改变外部调用 |
| `shrink:` | 长篇事故叙述与重复解释 | 保留职责、契约和必要设计理由；历史描述放 Git 历史，代码只描述当前行为 | 不估算全仓注释删减量 |
| `delete:` | 个人 fork 不需要的宣言入口与社区运营自动化 | 不提供签名/社区维护功能；保留 LICENSE、必要归属及工程 CI | 很小的业务简化，不是性能优化 |

**磁盘收益与代码收益分开看：** `docs/demo.gif`、`docs/vision-banner.jpg`、`docs/roadmap-phases.jpg`、`docs/og-image.jpg` 合计约 28.6 MB，是最大的资源面。可在个人版移除相应宣传内容或优化素材；有文档引用的要同步修复。这不会减少核心算法复杂度，也不会缩小已有 Git 历史。字体和 CV 视觉基线不应为省空间混删。

**实施优先级改为：先核对并收敛 Hermes 入口说明，随后完整删除 Web/TUI 及关联维护面，再退役不用的模型/分发入口，最后处理测试运行器与目录搬迁。** 保留现有 cron 三任务拆分；不将其重新合并为单个长任务。语言、插件、LaTeX 等仍属条件项。

## 4. 不能删除或不能这样精简的内容

1. **`providers/` 不是静态 import 清单。** `providers/_registry.mjs:23` 扫目录导入所有非 `_` 的 `.mjs`，`scan.mjs` 与 `verify-portals.mjs` 共用它。需要真实 `portals.yml`、全量扫描和外部发现需求一起决定可删源；不能仅凭当前公司列表或某次零命中裁源。
2. **`build-cv-html.mjs` 并未被 Reactive Resume 完全替代。** 当前 `modes/pdf.md` 要求结构化载荷先构建 HTML，交给 `verify-cv-facts.mjs` 检查，再由 Reactive Resume 渲染。删除 HTML 中间层之前，必须让事实校验直接覆盖规范载荷并证明等价；本次不把这项计入删除量。
3. **锁和原子写入仍然需要。** `pipeline-lock.mjs`、`tracker-utils.mjs` 的消费者包括扫描、状态更新、报告编号和 Web。单个 coordinator 只串行自己的任务，不能防止定时任务或另一个进程同时写。已有共享恢复逻辑，不能因为两个文件都提到 lock 就再造一个通用锁框架。
4. **身份归一化属于业务规则。** `url-key.mjs` 必须保留功能性 query，不能改为删全部 query 的一行代码；Unicode 公司名处理也不能换回英文字符正则。
5. **Web 镜像现在应随 Web 删除。** 不再为浏览器/服务器共享新建 package，也不迁移只服务于 Web 的适配层；核心 `url-key.mjs` 和 tracker 文本归一化仍保留。之前提出的 Web 共享代码重构已无必要。
6. **`jsonc-parse.mjs` 不能直接换 `JSON.parse`。** JSONC 的注释和尾逗号不是 JSON；仅在退役 OpenCode/JSONC 输入后才连同消费者删除。
7. **删 Gemini evaluator 还不能删 SDK。** `scan-hn.mjs:19`、`:83` 和 CI 检查仍使用 `@google/generative-ai`。要移除依赖，必须同时决定 HN 的可选 AI 提取能力；本报告不将该 SDK 算作 evaluator 裁剪后的既得收益。
8. **`dotenv` 现在不算死依赖。** 它在扫描和模型脚本被动态加载。个人版本若统一到 Node 24，可评估 `process.loadEnvFile`，但需保留既有环境覆盖、缺失文件和路径语义；根包目前声明 Node >=18，不能直接替换后仍声称支持原版本。
9. **测试夹具重复不一定需要抽象。** upgrade 不同版本的同内容快照表达各版本独立状态，复用一个可变对象可能削弱测试。不能通过删 fixtures 伪造精简。
10. **入口文件小是正常的。** `CODEX.md`、`CLAUDE.md` 已导入 `AGENTS.md`；非 Web 的短入口按实际宿主使用情况处理；`cn.ts`、`Button` 随 Web 退役，原因是产品能力删除，而非文件太小。
11. **Markdown 是持久事实，SQLite 是派生索引。** 不迁数据库为新真源。用户数据、报告、事实来源及审阅记录不计入删除目标；运行期锁、缓存也不能笼统执行清理。

## 5. 最小可用产品方案

Hermes 主宿主和 Web/TUI 退役已获明确场景确认；本轮仍仅交付分析，其余能力按消费者证据决定。

### 必须留下的完整行为

**A：** 配置岗位源 → 获取岗位/JD → URL 与内容去重 → 存活检查 → 四态预筛 → 源于证据的评估 → 发布报告与 Scored 清单 → 停止。

**B：** 用户选择一个 Scored 岗位 → 准备计划 → 生成真实的经历调整与申请问答 → 受管简历副本 → 独立审阅 → 修订与事实/PDF 验证 → 展示材料；由用户提交。

并行评估保留「worker 返回材料、协调者独占发布」的规则。无需另写模型路由框架、另建任务系统或同时维护 Claude shell 批处理。依赖 Hermes 完成推理、调度和通知；文件契约使中断后的恢复有依据。Hermes 当前加载的 skill、执行权限和工具能力需以安装实例为准，不能照搬 Codex 的线程 API 或假定多 agent 槽位相同。

### 最小组件

| 组件 | 复用当前实现 | 不增加什么 |
|---|---|---|
| 两个用户入口 | `modes/scan.md`、`pipeline.md`、`shortlist.md`、`apply.md` 等作为内部步骤 | 不为每个步骤新做页面/框架 |
| 获取与验证 | `scan.mjs`、`providers/`、`browser-extract.mjs`、liveness 系列 | 不统一所有 ATS 的差异为万能爬虫 |
| 预筛和发布 | `prescreen.mjs`、`lib/prescreen-*`、报告编号、pipeline 锁 | 不重写已有四态契约 |
| 申请材料 | `preparation-plan.mjs`、`application-artifacts.mjs`、`application-answers.mjs`、Reactive Resume、HTML/事实门槛 | 不削弱审阅或将母简历作为可写目标 |
| 数据读写 | tracker 解析、状态写入、原子写和锁 | 不新建服务、ORM 或第二个事实数据库 |
| 必要检查 | 源事实、输出校验、发布一致性与回归测试 | 不把覆盖率数字当成删测试的标准 |

运行时建议在下一次明确升级中统一到 **Node 24**，保留 `js-yaml` 和 `playwright`；这只是简化兼容面的目标，不是在本次修改 engines。Reactive Resume 作为已有外部后端保留其配置和凭据管理。是否完全移除 Gemini SDK、dotenv 取决于相关消费者迁移；尚不能承诺根依赖立刻只剩两个。

## 6. 建议最终目录结构

原则：**一层领域分组、一个数据真源、少量入口。** 不添加 monorepo 管理器、依赖注入容器、repository/service/controller 层或空目录。

```text
career-ops/
├── AGENTS.md                     # 工程/执行规则的主入口
├── .agents/skills/career-ops/     # 仓库标准 skill 入口；与 Hermes 安装入口保持单源
├── README.md                     # A/B 使用说明
├── DATA_CONTRACT.md
├── package.json
├── package-lock.json             # 若采用 npm，安装验证后生成并维护
├── config/                       # 保留现有用户配置路径
├── cv.md
├── article-digest.md
├── portals.yml
├── voice-dna.md                  # 可选用户源，存在则保留
├── writing-samples/
├── modes/                        # 保留流程文档，按需加载
│   ├── _shared.md
│   ├── _profile.md               # 用户层；不能被同步覆盖
│   ├── _custom.md                # 用户层；当前 A/B 规则
│   ├── _writing.md
│   ├── scan.md / pipeline.md / oferta.md / shortlist.md
│   ├── apply.md / pdf.md
│   └── ...                      # 只留下实际保留能力/市场需要的文件
├── src/
│   ├── discovery/               # 扫描、过滤、去重、页面读取与存活验证
│   │   └── providers/           # 沿用当前协议适配器
│   ├── evaluation/              # 预筛、证据缓存、评分结果校验
│   ├── application/             # 准备计划、问答、审阅、简历/PDF
│   └── storage/                 # 现有解析、身份键、编号、事务和原子写
├── scripts/                     # 运维和独立检查；无新调度器/消息网关
├── templates/                   # 现用布局与状态/领域契约
├── fonts/                       # 仅当保留模板确实引用
├── tests/                       # 领域回归、集成、fixtures、视觉验证
├── docs/                        # 数据格式与运维说明；不复制代码契约
├── data/                        # 保留现有持久路径与格式
├── reports/
├── jds/
├── output/                      # 保留当前逐申请 bundle 结构
├── documents/
├── interview-prep/              # 保留源事实和已有材料
└── .github/workflows/           # 保留测试与用户数据保护等有效 CI
```

这张树是**最终归属**，不是建议立即生成的 scaffolding。`src` 中优先移动原文件，只有两个实际消费者共享时才提取函数。参数解析与用例逻辑规模小的文件可继续放一起，不强求每个命令一层 wrapper。npm scripts 可直接指向领域文件，不必新增总 CLI。

Hermes 已安装 skill 位于仓库外，定时任务也保存在 Hermes 中；目录设计不复制它们的 scheduler、cron 数据库或 Discord 投递实现到仓库。仓库保留可重复调用的领域工具和现有持久文件。当前 `data/pipeline-runs/` 保留中断材料；`data/pipeline.md` 继续作为岗位队列，不加第二个 queue.json。

**cron 兼容优先于目录美观。** 第一轮删除 UI 时保持 `node scan.mjs` 等现有路径。上面的 `src/` 是以后归位的目标；只有在同时更新仓库引用、Hermes skill 和全部 cron 消费者时才执行移动，不额外保留永久双份实现。

如果继续追随上游自动更新，**目前保持根脚本路径更便宜**：`ARCHITECTURE.md` 明确记录了路径稳定性；`update-system.mjs` 维护系统路径白名单。独立目录重构意味着系统所有权与更新策略也需决定，不能改完结构又让旧更新器恢复旧树。先做保留路径的裁剪版本，再单独决策是否成为自主维护的 fork。

## 7. 建议迁移顺序与验收

| 顺序 | 改什么 | 完成条件 |
|---|---|---|
| 1 | 以已存在三个 Hermes cron 和生产根为基准，收敛重复 skill/日报说明 | 规则不互相矛盾；保留现有触发次数、预算、岗位上限和通知意图 |
| 2 | 完整退役已明确不用的 Web/TUI，再处理独立执行器 | 同时清理 npm/Go 依赖、CI、模式入口、当前文档及专属测试；共享约束保留 |
| 3 | 测试运行器与重复参数处理收敛 | 原行为检查全部保留；故意失败的测试仍令总命令非零；临时文件与进程正确隔离 |
| 4 | 按 discovery/evaluation/application/storage 移动实现 | 修改 import、spawn、cwd、资源路径、测试发现、系统路径清单；没有残留旧入口或重复实现 |
| 5 | 用隔离的代表性数据走 A/B | A 只到 Scored；B 仅选定岗位触发；历史报告号可复用；无用户事实改写 |
| 6 | 做与保留能力匹配的检查 | 并发写不丢数据、存活失败不当零结果、预筛未知不当失败、事实门槛有效、中英文 PDF 可读；不再运行 Web/TUI 构建；改为验证 Hermes 工具调用和三个 cron 的端到端输出 |

目录/CLI 是真实外部接口。若有外部消费者，迁移前应给出一次明确取舍；不要默认永久保留旧路径 wrapper，也不要在消费者未迁移时直接破坏它。用户历史产物路径不因目录整齐而改变。

## 8. cron 场景必须保留的工程能力

- **独立运行与有限预算：** scan 按 provider 保存已有结果，score 最多 30 条并允许部分完成，report 不等待 Pending 清空。不能为简化代码取消这些边界，也不新建工作流引擎。
- **已有检查点与幂等：** 复用扫描历史、完整预筛缓存、报告编号和 `pipeline-runs/` staging；重跑不重复评分、不覆盖已有申请副本。保存结果与投递消息分开，report 只读。
- **跨进程协调：** 当前 cron prompt 使用根目录 `.pipeline.lock`，代码另有 pipeline/tracker 锁。它们职责是否重叠要沿实际路径核对；建议复用已有带所有权/恢复语义的锁机制，保持统一顺序，不再引入第三套锁或只靠时间错开。不能把整轮任务互斥与短暂文件事务锁不加区分地合并。
- **状态与输出：** scan/score 静默，report 每日必发；不要把「没变化不通知」通用习惯套进此日报。统计取自真实记录，不将报告 mtime 自动当作首次评分时间。
- **宿主边界：** 模型凭据、选择、重试调度与 Discord 交给 Hermes；领域提取、事实校验、状态写入留在仓库。保留 Playwright CLI；若 fallback 依赖 MCP，必须验证 Hermes 实际加载了相应工具，不能因为 `.codex/config.toml` 存在就判定可用。
- **维护隔离：** 不在日常 cron 中实施仓库升级、依赖更新、数据 onboarding 或目录迁移。先在隔离数据上验证，再安排切换生产消费者；本次不改已有 job。

以上关注结构和责任边界；没有展开安全漏洞或并发正确性的独立代码评审。

## 9. 修正后的收益与证据

**明确退役范围：`web/` + `dashboard/` + `build-dashboard.mjs`，共 260 个文件、41,120 行文本。** 这是待删除文件的毛量，不包含散落在根测试、updater、CI、文档中的关联清理，也不是已执行的净 diff。

Web 的 12 条运行依赖声明 + Go 的 5 条直接依赖声明 = **17 条可移除声明**，不含开发或传递依赖，也不等于 17 个全仓唯一包（根包仍使用 `js-yaml`）。shader 已包含其中，不再另计。实际删除还需同步移除 Web/TUI 专属构建任务，保留非 UI 检查。

此前 444 文件 / 72,757 行的总候选中，其余 **184 文件 / 31,637 行** 仍需核对语言、插件、执行器、LaTeX 消费者。原来的「约 7 万行净减」不再作为主要承诺；本场景先按已经明确放弃的 41,120 行文件面立项，净值以后续可运行 diff 为准。

本次额外读取了 Hermes 任务配置、两个 skill 及相关引用，并抽查生产核心文件与审查 worktree 一致性。没有改 cron、skill、业务源或数据，没有触发任务、发送消息、安装依赖或执行运行验收。初审中记录的 Node 工具检查仍有效，但不代表生产 Gateway 的运行环境。

net: -41,120 lines, -17 deps possible.（已确认退役文件的文本毛量；实际净差额待实现，deps 指直接声明。）
