# LinkedIn 链路 ponytail 审查

What this change does: 原链路从搜索页发现职位，用完整详情生成标准记录，并在 429 后有限重试。来源采集受同一个固定截止时间约束，Python 负责后续规则过滤、去重和业务发布。

审查范围为 `f683419a` 的 LinkedIn DOM 提取及 `3b4ec305` 的退避修改，连同真实调用方 `_collect.mjs`、`discovery/configured.py`、已有身份解析器及相关测试。按当前单用户、两个 LinkedIn 来源、四个关键词、每来源最多 100 个结果和 525 秒采集窗口评估，没有按大规模服务设计。

## Must fix

1. **不能在服务端要求的等待时间之前重试**（`adapters/node/providers/search.mjs`，`requestWithRateLimitRetry`）
   - **What this is:** 本地等待上限防止一次请求占用整个来源预算。
   - **Problem:** `Retry-After: 120` 被截为 60 秒，相当于明知服务端要求至少等两分钟，却提前重试。原测试还固定了这一行为。
   - **Fix:** 先计算服务端要求与默认退避的较大值；若超过本地 60 秒上限，放弃当前请求并继续其他队列。保留同一个 deadline。已实现，并验证 30 秒头按要求等待、120 秒头不提前重试。
   - **If we skip it:** 白费请求与预算，仍可能持续被限流。

2. **职位身份必须来自真实职位路径**（`adapters/node/providers/search.mjs`，`postingKey`；`browser/browser-extract.mjs`，LinkedIn DOM 提取）
   - **What this is:** 身份校验决定页面证据是否属于请求的职位。
   - **Problem:** 自行复制的未锚定正则会把 `/foo/jobs/view/123` 当成 `/jobs/view/123`。已用 provider 与浏览器回归分别复现：前者未抛错，后者错误生成了 JobPosting。
   - **Fix:** Node 侧复用现有 `linkedInJobId`；DOM 边界使用一个严格路径解析函数同时检查当前路径与 canonical，删除重复正则。两项回归均从失败转为通过。
   - **If we skip it:** 不属于同一职位页面的 canonical 或结构化 URL 可能被错误接受。

3. **恢复成功的重试不能进入最终失败统计**（`search.mjs` 退避日志 → `configured.py:collect_provider_results`）
   - **What this is:** Python 将 Node stderr 的每一行作为覆盖警告，并计入 discovery 失败列表。
   - **Problem:** 每次正常重试都写 stderr；即便恢复成功，正式结果仍会多记错误。上一轮原始日志中有 15 条此类过程消息。
   - **Fix:** 删除正常重试的 stderr 输出，只保留最后未恢复的错误。没有新增日志前缀、过滤器或兼容分支。回归确认成功重试不输出失败警告，重试耗尽仍报告错误。
   - **If we skip it:** 正式入库结果会把正常恢复误报为采集失败，掩盖真正失败项。

## 简化后的边界

- 一个固定的外层 deadline，来源窗口只从它派生；移除“先减预留，再加回去构造 context”的往返转换。
- 队列只决定搜什么、读什么、失败后继续哪一项；一个局部重试函数决定是否等待并重试。
- 浏览器层继续负责 URL 安全、HTTP 状态、导航与内容读取；共享导航间隔不能因某个来源到期而永久失败。
- JD 校验保留标题、雇主、实质正文和身份绑定。没有为了增加通过率放宽校验。
- 没有新增依赖、策略配置、通用重试框架、持久队列或 fallback 链。

验证通过：provider 回归、hydration 浏览器回归、240 个 `.mjs` 语法检查，以及 `tests/business/workflow-scan-test.py`。正式 discovery 与业务验收另存运行记录。

Verdict: Ship. 三项问题已在正式运行前修正。

Lean: `postingKey` 函数体减少 2 行，另删除一条错误层级的过程日志；生产逻辑总行数没有增加。

Not checked: LinkedIn 长期限流变化和多主机并发；当前仅有单用户本机运行需求。
