# OII-397：GitHub 三维研究替代实现调研

核验日期：2026-10-09。固定提交和依赖以 GitHub API、raw.githubusercontent.com 直接响应为准，main 网页缓存可能滞后；本次公开响应/源码快照保存在 `/tmp/oii-github-research/`（临时核查，不是业务证据库）。范围：公开 GitHub README、实际研究/压缩源码、依赖及许可证；未安装候选、未运行付费研究、未修改正式流程。排序按与 Career Ops 的适配性，不按 stars 或官方性能宣传。

## 结论

有可移植实现。优先验证 **LangChain Deep Agents 的 deep_research 示例 + harness**：它补充的关键能力是可回读的材料外置、研究过程中的自动摘要和隔离子研究上下文，而不是又一套最终报告 map/reduce。第二选择 **GPT Researcher** 的 Python 研究入口；适合希望直接复用搜索、抓取、引用和递归探索的人，但其依赖和过滤口径更重。**Open Deep Research** 可借鉴 focused researcher / compress_research，已归档，不宜作为整体持续依赖。**dzhng/deep-research** 很短，适合作算法参考，不适合原样替代目前有来源留存和恢复要求的正式流程。

这只是源码适配判断。没有证据能证明移植后成本更低、搜索更充分或中国公司的 culture/compensation 更准，必须用同公司、同 scope、同模型和搜索服务做隔离 A/B。

## 已核验候选

| 仓库 | 本次 main SHA | 状态与许可 | 适配判断 |
|---|---|---|---|
| [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) | `efd88ff8fd1279361de77a83c9f75d98ed2f36d5` | 未归档；主分支提交 2026-10-08；MIT | 最贴近 Python/LangGraph；接入 harness，不复制整库 |
| [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | `0957c301ed06c2a5857b834358c7227c739041d4` | 未归档；主分支提交 2026-09-26；Apache-2.0 | Python API 可用；额外 embedding/爬取/报告系统较重 |
| [langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research) | `1b7d2e80db9faa586165c60e09096dbbfd483a64` | 2026-08-21 归档；MIT | 抽取研究子图思路；不把整个归档应用接为正式核心 |
| [dzhng/deep-research](https://github.com/dzhng/deep-research) | `1f8f3e285bbc23e80b98a66a64effab9069f3ad4` | 未归档；主分支提交 2026-04-11；MIT | 小巧，但 TS/Firecrawl 和来源、恢复缺口增加改造量 |

状态、时间及许可通过 [Deep Agents API](https://api.github.com/repos/langchain-ai/deepagents)、[GPT Researcher API](https://api.github.com/repos/assafelovic/gpt-researcher)、[Open Deep Research API](https://api.github.com/repos/langchain-ai/open_deep_research)、[dzhng API](https://api.github.com/repos/dzhng/deep-research) 核验。移植保留对应 LICENSE/版权声明；Apache 代码按其许可证处理 NOTICE（如果所移植分发包含）。提交日期是主分支快照，不等同于发布版本，也不是质量指标。

### 1. Deep Agents：首选隔离试验

[研究示例 agent.py](https://github.com/langchain-ai/deepagents/blob/efd88ff8fd1279361de77a83c9f75d98ed2f36d5/examples/deep_research/agent.py) 使用 `create_deep_agent`，配置 research-agent 子代理、Tavily、think_tool 和三并发/三轮提示参数。[tools.py](https://github.com/langchain-ai/deepagents/blob/efd88ff8fd1279361de77a83c9f75d98ed2f36d5/examples/deep_research/research_agent/tools.py) 搜索 URL 后用 httpx 抓正文、markdownify 转换，返回标题、URL 和内容；默认每搜索仅一条结果。它不自动解决登录、反爬或网页缺失。不能照搬示例短搜索次数并声称资料更充分。

[graph.py](https://github.com/langchain-ai/deepagents/blob/efd88ff8fd1279361de77a83c9f75d98ed2f36d5/libs/deepagents/deepagents/graph.py) 接受预配置 BaseChatModel、工具、backend、结构化 response_format 和 checkpointer，并装配 filesystem、subagent、summarization middleware。因此可传当前 OpenAI-compatible ChatOpenAI、关闭 Responses API 偏好、提供现有 Tavily 工具和保留来源目录。但 endpoint 对工具调用、结构化输出、usage/reasoning metadata 的实际兼容性还没运行验证。checkpointer 参数只是能力入口，示例没提供我们的恢复/提交契约。

[filesystem.py](https://github.com/langchain-ai/deepagents/blob/efd88ff8fd1279361de77a83c9f75d98ed2f36d5/libs/deepagents/deepagents/middleware/filesystem.py) 能把大工具结果外置并返回预览/文件位置，后续通过文件工具回读；默认门槛为单结果约 20K tokens，以字符近似判断。**门槛可能比我们当前 read_sections 的块还大，默认安装不一定触发。** 原始材料和存取引用仍应由现有证据存储负责；工具可直接保存来源文件后返回引用和预览，不必依赖超大返回结果才外置。

[summarization.py](https://github.com/langchain-ai/deepagents/blob/efd88ff8fd1279361de77a83c9f75d98ed2f36d5/libs/deepagents/deepagents/middleware/summarization.py) 有模型 profile 时默认在输入窗口的 85% 摘要、保留 10%；无 profile 默认 170K 输入 tokens。**这是单次上下文触发值，不是累计 token 预算。** 当前150K累计研究预算可能在触发前耗尽，未知自定义模型也可能没有正确 profile。试验必须显式配置真实上下文与触发条件，记录摘要是否发生和后续是否实际回读被压缩材料，不能照搬 85%。

[依赖定义](https://github.com/langchain-ai/deepagents/blob/efd88ff8fd1279361de77a83c9f75d98ed2f36d5/libs/deepagents/pyproject.toml) 的源码版本为 0.7.23，要求 Python≥3.11、langchain≥1.4.4、langchain-core≥1.6.7，以及 Anthropic/Google 等依赖。本地当前 langchain 1.4.3，需要隔离依赖验证或选已核验兼容的发布版本，不能直接把 main 装进正式环境。接入成本判断：中等；研究循环可复用，但来源、预算、usage 和恢复必须接现有约定。

### 2. GPT Researcher：现成程度高，控制面较重

[deep_research.py](https://github.com/assafelovic/gpt-researcher/blob/0957c301ed06c2a5857b834358c7227c739041d4/gpt_researcher/skills/deep_research.py) 生成搜索问题，通过每查询 GPTResearcher 研究，抽取 learning + sourceUrl + followUpQuestions，按 breadth/depth 递归、Semaphore 控并发，返回 citations、visited_urls、sources、context。它维护最近 context 并按 25K **词**截断，失败查询返回 None，全部失败停止。breadth/depth 是探索控制，不等价于200K累计 token限制；截断不等于无损保留。适合直接调用研究入口，但不要默认接其报告和评分系统。

[compression.py](https://github.com/assafelovic/gpt-researcher/blob/0957c301ed06c2a5857b834358c7227c739041d4/gpt_researcher/context/compression.py) 将材料切为1000字符/100重叠，embedding similarity 过滤，默认阈值0.35；小材料可跳过滤。它增加 embedding 模型、成本及材料发送目的地，不能因已授权研究 LLM 就默认发送到另一个 embedding 服务。相似度过滤可能漏掉反证、地域限制、奖金条件，尤其需要 culture/compensation A/B，不能把它作为充分性推荐门槛。

[generic/base.py](https://github.com/assafelovic/gpt-researcher/blob/0957c301ed06c2a5857b834358c7227c739041d4/gpt_researcher/llm_provider/generic/base.py) 明确支持 OPENAI_BASE_URL、DeepSeek provider 和 usage metadata。研究可搭 Tavily；现有轮换和错误留存仍须由我们统一接入。未核验它有满足本地200K分维预算和阶段恢复的现成实现。接入成本判断：中到高；若整库接入，维护面明显超过换研究循环本身。

### 3. Open Deep Research：结构合适，归档与降级行为不合适

[deep_researcher.py](https://github.com/langchain-ai/open_deep_research/blob/1b7d2e80db9faa586165c60e09096dbbfd483a64/src/open_deep_research/deep_researcher.py) 有 supervisor→并行 researcher→compress_research→final_report；子研究使用工具循环并在结束时压缩，返回 compressed_research 和 raw_notes。**末尾压缩没有让研究循环自动压缩历史**，研究阶段仍传累积消息。代码含任意子研究异常结束 supervisor，以及压缩超限时删除旧消息、最终超限时截短 findings；不能原样移植为正式恢复行为。

[configuration.py](https://github.com/langchain-ai/open_deep_research/blob/1b7d2e80db9faa586165c60e09096dbbfd483a64/src/open_deep_research/configuration.py) 支持不同研究/压缩/报告模型与迭代、并发控制；[utils.py](https://github.com/langchain-ai/open_deep_research/blob/1b7d2e80db9faa586165c60e09096dbbfd483a64/src/open_deep_research/utils.py) 接 Tavily/MCP 等工具。custom base URL 及当前模型完整兼容仍需改适配，不是换模型字符串即可证明。子图编译未见持久 checkpointer 绑定；默认用法不能证明本地断点恢复。接入成本判断：抽 researcher 子图中等，整体移植高且维护责任转给我们。

### 4. dzhng/deep-research：最短，但不是最小接入成本

[deep-research.ts](https://github.com/dzhng/deep-research/blob/1f8f3e285bbc23e80b98a66a64effab9069f3ad4/src/deep-research.ts) 生成查询→Firecrawl 搜索抓Markdown→抽 learnings/后续问题→深度递归（breadth减半），p-limit 控并发；继续时带 learnings 而非全工具会话。visitedUrls 收集后附在报告末尾，learning 本身没有 sourceUrl 映射。分支出错返回空 learning/URL；没看到持久 checkpoint 或累计预算入口。

[providers.ts](https://github.com/dzhng/deep-research/blob/1f8f3e285bbc23e80b98a66a64effab9069f3ad4/src/ai/providers.ts) 支持 OPENAI_ENDPOINT/CUSTOM_MODEL，但通过 trimPrompt 截前缀控制上下文。需要把 Firecrawl 改成现有 Tavily、补来源和恢复，并引入/桥接 TS AI SDK 或重写成Python。接入成本判断：中到高；短源码不抵消数据契约缺口。不推荐为这三个维度新增 Node 研究编排。

## 相比现有流程，新增什么

| 能力 | 当前已存在 | 候选真正补充 |
|---|---|---|
| 三维独立 agent、company/scope 复用 | 已有 | 不是收益依据 |
| Tavily、原文留存、独立摘要、Jev评分 | 已有 | 保留，不能重建旁路 |
| 16K分批摘要、32K合并 | 已有 | map/reduce 不是新增能力 |
| 研究过程工具全文反复进入history | 当前每轮重发history | Deep Agents 可回读 offload + rolling summary；另外两种 learning 状态驱动可作参考 |
| 200K/维累计预算、阶段恢复、SQLite提交 | 已有本地边界 | 没有候选自动符合，需适配保留 |

当前实现基线由主流程源码核验提供：研究150K + 最终摘要剩余额度至200K/维；Tavily credits限制单独存在。候选默认 depth/轮数/上下文上限不是同一种预算，不能混算。

## 最小移植切片和验证范围

1. 用隔离环境接入 **Deep Agents harness + 示例研究提示思路**，替换单个维度的 research/summary 入口；复用现有 Tavily 搜索、抓取、source captures，不接示例UI、LangGraph服务、额外监督报告或评分系统。三个维度各运行独立实例，避免新增一个通用监督者反复拆分我们已确定的三维。
2. 工具写原文文件，只返回 source_id、URL、标题、捕获时间、scope、预览与可回读位置；分维摘要保留事实、地域/层级/生效时间、数字单位、奖金/股权条件、冲突和未找到项的来源引用。工具失效/登录不可读单独记录，不能伪装为“该信息不存在”。不重新引入摘要逐字/哈希匹配门槛。
3. 每个 agent **独立200K累计 tokens**覆盖研究、所有 compaction、恢复重试和最终摘要；保留目前150K研究与摘要余量策略，usage不明记录不明，禁止当0。没有三个维度共享总预算。新增子代理时，其token也计对应维度，不能靠嵌套逃过额度。充分性可作研究事实说明，**不成为推荐gate**；最终仍三次Jev维度评分，方向保持per job。
4. 用当前Microsoft三个scope做同模型/搜索服务的冷运行对照，再加入至少一个中国本土公司；固定as_of、输入和测量口径。分别量总token、LLM/搜索次数、耗时、费用、失败/恢复、找到的新增适用事实与数字条件丢失。保证至少一次真实offload/compaction、一次回读、一次恢复；使用原始来源审查关键薪资/工时事实。评分变化单列，不能把变化本身当正确性提升。

**本轮没有执行移植或上述付费 A/B。** 下一步最有价值的是这个小适配试验，成功后再替换三个研究入口；现在没有理由整体迁移某个应用，或声称其公开bench能代表公司薪资/文化质量。
