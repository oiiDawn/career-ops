# OII-397：Jev 辅助摘要与 compaction 调研

日期：2026-10-08。范围：只调研 company、culture、compensation 三个独立维度的文本组织与压缩；未调用 Jev、未运行付费实验、未改算法、预算或调度。

## 结论

**已核实：Jev 有官方现成的段落筛选模式，但没有本次查阅发现的原生摘要生成或 compaction 接口。** 它输出 Choice、Score、Noul 决策；摘要文字仍应由生成模型产生。最直接可借用的是官方 `Classifying RAG passages` cookbook：Jev 判断段落，代码筛选，Claude 写答案。不能把这个混合流水线称作“Jev 生成摘要”。[Introduction](https://docs.typesafe.ai/introduction)、[API reference](https://docs.typesafe.ai/api)、[官方 RAG cookbook](https://docs.typesafe.ai/cookbooks/classifying_rag_passages)

**建议：暂时保留当前分批摘要再合并。** 若实际瓶颈是研究阶段反复发送历史工具正文，先比较研究历史 compaction；若瓶颈是末尾摘要处理大量无关段落，再比较 Jev 筛选后摘要。二者解决不同开销，可以分别实验，不能靠供应商单次调用宣传推断总流程更快。

## 已核实的当前实现

工作区实现为 [company_pipeline.py](/Users/oii/dev/career-ops/career_ops/evaluation/company_pipeline.py:392) 与 [adaptive_research.py](/Users/oii/dev/career-ops/career_ops/evaluation/adaptive_research.py:252)，以下为本次直接读代码所得：

- 三维独立运行。每维总 token 预算 200K，研究预算 150K，摘要至少保留 50K；研究少用时剩余额度可用于摘要。**总调用用量预算不是单次模型上下文长度。**
- 研究保留 provider 返回的完整正文；末尾摘要实际接收的是已读 sections 与 source header，不等同于把所有完整页面喂入模型。
- 摘要输入按估算 16K 分批，超长来源分片；部分摘要按 32K 分组合并直到只剩一份。调用与合并共享剩余预算，JSON/长度问题最多修复一次。
- 摘要保留 claim、日期、适用范围、限制、来源 URL/ID、gaps、conflicts；结构检查并不证明事实语义正确，当前 `claim_semantics_verified=False` 如实表达这一点。
- 研究循环把模型响应与工具结果追加到历史，后续调用再次发送历史；当前读取的循环没有历史 compaction 步骤。

因此，这次讨论应区分三个位置：研究历史压缩、原文段落筛选、末尾事实摘要。full sources 继续留在磁盘作为复查依据；压缩只改变后续模型看到的活动上下文。

## Jev 到底能做什么

### 现成模式：提取式筛选，不生成新摘要

官方 RAG cookbook 对每个 query–passage pair 提出四个 Noul：相关性、是否含可用证据、是否反驳查询前提、是否含提示注入。代码将段落送入证据块、冲突块或排除；最终生成由 Claude 执行。文档明确示例阈值仅针对该 corpus，须在自己的数据上调整。本例使用 `jev-1.12`，不能直接当作当前模型和职业信息领域的验收证据。[Classifying RAG passages](https://docs.typesafe.ai/cookbooks/classifying_rag_passages)

另一个官方 cookbook 用 Choice 在已编号行中排序，并用 Noul 检查文档是否真的含答案。Choice 概率总和为 1，即使完全无关也会有第一名；因此只取 top-k 容易制造“必然有答案”的假象。单个 Choice 最多 255 个选项。[Line-by-line search](https://docs.typesafe.ai/cookbooks/semantic_find)、[Choice API](https://docs.typesafe.ai/api)

**本项目的建议性映射：**

| 维度 | Jev 可协助判断 | 不能因低相关分直接丢掉的限定 |
| --- | --- | --- |
| company | 段落是否涉及持续经营、工程投入、当地缩编、管理层变化 | 法人/地区/日期、一次性事件与持续趋势、反向证据 |
| culture | 是否提供实际工时、加班、假期、协作或社保公积金执行信息 | 官方承诺与员工执行、法定底线与额外待遇、受访群体和代表性 |
| compensation | 是否含目标地区/岗位族/职级的薪酬或支付条件 | 保证与浮动、税前口径、奖金资格、股权归属、币种、是否真实 offer |

这是设计推断，并非现成职业信息 cookbook。实现候选应保留完整段落和关联表头/上下文，筛选结果由代码复制原文，再交现有摘要器。Jev 的请求问题 key 只是映射答案，官方 API 说明 key 不传给底层模型；段落定位、维度和范围必须写进实际 state/instructions，不能只靠 `culture_17` 之类命名。[API reference](https://docs.typesafe.ai/api)

### 能力边界与现行限制

官方 `Jev 1.13 jaggedness` 明确：Jev 不接受自由文本生成任务；通过串联 Choice 强迫生成会慢且效果差；无关大 state、复杂间接关系、数字精度、日期比较、对抗文本、Choice 顺序都存在已知问题。文档建议先筛选相关材料，必要时用 Noul 做相关性筛选。该页最后审阅日为 2026-10-02。[模型已知限制](https://docs.typesafe.ai/model-jaggedness/jev-1.13)

当前官方 Models 页列 `jev-1.13.0`：每请求总计 64K，state 加最长单题不得超过 32K；文本输入 $0.042/M token，输出免费；支持 CJK，但英文准确度最好，其他语言应自测。100K token/s、80 request/s 限流明确可能调整。大批材料必须分批，不能把每维 200K 总预算当 Jev 的 200K state。[Models](https://docs.typesafe.ai/models)

Choice/Score confidence 来自概率分布，Noul 不另给 confidence。分布集中不构成事实正确性、召回完整性或范围匹配的独立证明；职业领域的丢弃策略须由人工标注样本验证。[Confidence](https://docs.typesafe.ai/confidence)

**查阅范围：** 由 [TypeSafe 官方首页](https://typesafe.ai/) 跳转官方 docs，读取 [完整文档索引](https://docs.typesafe.ai/llms.txt)、Introduction、API、Models、jaggedness 与上述 cookbooks。docs 链接的 [官方 GitHub organization](https://github.com/typesafe-ai) 提供 SDK 和公共示例。未在这些公开接口与索引发现 `summarize`/`compact` primitive；此结论限定于公开可查文档，不声称不存在任何内部方案。`typesafe-jev.com`、`jevtypesafe.org` 等非官方域名未作为依据。

## Compaction 与当前摘要的区别

Anthropic 定义的 compaction 是把旧会话压成摘要，并用摘要继续后续上下文；它针对持续研究/工具循环，不是单次对所有 source 做终稿。官方工程建议先保住召回，再去冗余，并指出过度压缩会丢掉后来才重要的细节。[Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

Claude 当前有服务端按需 compaction 和 token 阈值 compaction，另可在客户端自建摘要器。按需接口返回摘要及签名 block，必须按原样带回 Claude；调用仍收费，后续压缩会再次概括旧摘要与新历史。签名保证 block 未被改写，并不验证摘要事实；此服务端形态也不能原封不动当成 Jev 原生接口或本项目通用生成供应商接口。[Compaction overview](https://platform.claude.com/docs/en/build-with-claude/compaction)、[On-demand compaction](https://platform.claude.com/docs/en/build-with-claude/compaction-on-demand)

**建议性通用实现思路：** 研究循环接近活动上下文上限时，由现有生成模型整理“已支持事实/冲突/未知/已经查过的来源/下一步缺口”，替换旧工作历史，保留近几轮完整消息及完整的工具调用与结果配对。工具正文在磁盘保留，后续通过已有 `read_sections` 按需回读。末尾摘要仍从 retained read sections 生成，避免“摘要的摘要”变成唯一证据来源。若仅清除陈旧工具正文就足够，应先测这一轻量方案；Anthropic 将工具结果清除列为独立 context editing 方式。[Context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)

## 方案比较

以下比较为基于实现和文档的推断，尚无本项目新实验数据。

| 方案 | 能省哪里 | 新增开销 | 主要风险 | 建议顺序 |
| --- | --- | --- | --- | --- |
| 当前批次摘要→分层合并 | 已避免一次塞入所有来源 | 多个摘要/合并调用 | 跨批冲突、限定语在合并时丢失；超长分片切断上下文 | 保留为对照 |
| 研究历史 compaction | 后续研究调用不再反复携带旧长历史 | 压缩调用与后续摘要重读成本 | 早期遗漏固化；已查来源/缺口丢失导致重复查；顺序依赖 | 历史重复输入确为瓶颈时优先 |
| Jev 段落筛选→现有摘要 | 减少末尾摘要的原文输入 | Jev 全文筛选输入、问题、请求与重试 | 假阴性把关键事实/反证/适用限制一起删掉 | 无关正文占比高时再试 |
| Jev 筛选→直接 Jev 评分 | 跳过生成摘要 | 筛选和评分仍两段 | 未整理来源冲突，长表/多范围输入影响评分；报告仍需解释 | 不作为本次默认建议 |
| LLMLingua token 压缩 | 给下游的 token 数 | 新模型、权重、推理与依赖维护 | 字词级删除影响否定、日期、金额、表格关联；跨模型质量不确定 | 暂不引入 |

LLMLingua 是实际开源现成压缩器，并非 Jev 插件。LLMLingua-2 使用 token 分类和小型 encoder 做提取式压缩；原论文报告自己的数据集结果，不能转移成中文职业证据上的质量保证。[微软原仓库](https://github.com/microsoft/LLMLingua)、[LLMLingua-2 原论文](https://aclanthology.org/2024.findings-acl.57/)

仓库提供 `rate`、`force_tokens` 和可不压缩的结构化区块，可用于保护元数据。但强制保留某些词不等于保证整个事实关系正确；对于当前需要来源可追、金额条件完整的任务，先做整段筛选比字词级压缩更容易人工检查。这是本项目建议。[微软原仓库使用示例](https://github.com/microsoft/LLMLingua#usage)

## 成本判断与可验证的小实验

**已核实价格，未实测收益：** 按官方当前 Jev 输入价，100K billed input tokens 是 $0.0042。但每段请求重复的范围、问题与元数据也要算；批次里的 questions 同样占上下文。新增筛选省的是下游生成模型输入，不一定减少整体调用数或等待时间。应记录实际 usage，重试与限流，不拿“源文字只有 100K”直接算最终账单。[Models](https://docs.typesafe.ai/models)、[API usage](https://docs.typesafe.ai/api)

滚动 compaction 也不是免费：每轮继续研究会重复发送 running summary，重新压缩时再付摘要输入/输出成本。只有被省掉的旧历史重复输入大于这些新增成本才有收益。生成供应商当前实际结算价、本语料的筛选保留率、质量损失和最终报告耗时均未在本次测量，盈亏平衡点保留未知。

建议一次冻结同一批已留存来源，不重新联网扩展语料，先跑 A/B/C：A 当前实现；B 相同研究历史加入 compaction 的离线回放；C 原文整段经 Jev 筛选后调用相同摘要器。B 衡量研究继续任务，C 衡量末尾摘要，分别比较，不把不同任务总耗时相减。实验需另外明确运行预算；本次没有发起。

1. 三维各选少量高风险来源：中文员工工时、官方福利与实际执行矛盾、薪酬表与适用城市、保证/浮动/股权、未披露数据、不同日期和企业实体。保留中英文与长短页面组合，固定模型版本与摘要参数。
2. 人工列每个样本的必留事实和限定语，不要求摘要逐字相同。看事实召回、条件保留、错误新增、冲突保留、未知是否仍未知、来源能否方便人工回查；无需精确引用匹配、offset 或严格 hash 语义门禁。
3. 对筛选器优先量关键事实假阴性和 retained token ratio；不确定段落保留，矛盾证据不按“低相关”删除。先从宽松保留策略探索压缩收益，再调阈值。
4. 对 compaction 记录重复输入下降、额外压缩成本、来源回读、重复查找和缺口跟进；至少改变一遍来源顺序，检查早期遗漏与旧摘要反复压缩漂移。
5. 全流程记输入/输出/推理用量、调用数、失败/修复/重试数、wall time；仅在相同事实质量下比较总成本。后续若获准评分比较，关注分数/证据充分性是否变化及变化原因，不能把“分数一致”当事实完整。

**建议验收原则：** 关键金额/工时/地区/职级/保证条件不能漏或被改写成更强事实；冲突和 unknown 不因压缩消失；复查路径保留。只有满足这些条件且测得总成本或耗时下降，才值得改正式流程。当前资料支持做小实验，尚不支持替换正式算法。
