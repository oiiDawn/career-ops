# eFinancialCareers 最小修复与只读验证

What this change does: 搜索结果进入详情读取前，只保留 eFinancialCareers 的 `/jobs-….id数字` 职位 URL。候选去重、跳转检查和结构化 JD 身份校验共用稳定职位 ID，职位改名不会改变身份。

## Ponytail 审查

按单用户本机、一个香港来源、四个共享关键词、最多 50 个有效职位评估。检查了 `collectSearch`、`postingKey` 的全部调用方、`jobFromPage`、真实浏览器读取、Node collect 入口和 Python 收集边界。没有改来源配置、关键词、分页、访问安全检查、完整 JD 校验或 403 停止策略。

### Must fix（均已修复）

1. **把非职位页面交给详情读取器**（`adapters/node/providers/search.mjs:195`）
   - **What this is:** Web 搜索覆盖整个 `efinancialcareers.hk` 域名，返回新闻、职位列表和真实详情的混合结果。
   - **Problem:** 原实现只检查域名范围，随后对所有结果要求单一 JobPosting。新闻、分类页自然失败，还可能在这些页面遇到 403 后停止来源。
   - **Fix:** 在现有候选队列边界筛选真实详情路径，复用下述 ID 解析。非职位页面是正常跳过，不放宽 JD 校验，也不误报为详情失败。
   - **If we skip it:** 继续浪费浏览器导航，并把不属于职位详情的页面算成采集故障。

2. **职位改名导致同 ID 被误判为不同职位**（`search.mjs:82–94`）
   - **What this is:** 页面与结构化 JD 的 URL 都带稳定职位 ID，但标题部分可能不同。
   - **Problem:** 第一轮验证发现 `Data_Science_Practitioner.id24760865` 的页面提供 `Senior_Data_Scientist.id24760865`。完整 JD 存在，旧校验却因比较整条 URL 而拒绝。
   - **Fix:** 一个内部 ID 解析函数同时用于候选筛选与 `postingKey`；相同 ID 才能匹配和去重。不同 ID、错误路径和其他站点继续被拒绝。不增加配置或站点适配框架。
   - **If we skip it:** 一部分真实职位仍被错误排除，改名链接还可能重复读取。

生产实现增加 12 行，回归增加 23 行。没有新增依赖、公共接口、配置项或持久恢复机制。

## 测试

- 候选筛选回归修改前失败：新闻和分类页被读取并消耗有效结果额度；修改后仅访问真实详情，后续关键词继续执行。
- 身份回归修改前失败：同 ID 的改名 URL 被重复读取且拒绝；修改后匹配并去重，不同 ID 仍拒绝。
- `node tests/adapters/providers/search.test.mjs` 通过，已有 LinkedIn 重试、来源范围和完整 JD 验证仍通过。
- `node scripts/check-syntax.mjs`：240 个 `.mjs` 通过。
- `.venv/bin/python -B tests/business/workflow-scan-test.py` 通过。

## 不写业务库的真实验证

直接运行正常 `adapters/node/providers/_collect.mjs` 的 collect 入口和真实 search provider；没有调用 Python discovery 发布、BusinessStore、资格初筛或评分。证据写在 `data/cache/efinancialcareers-validation-20261018/`，未写业务库。

输入为真实来源配置：AI、AI Agent、Full Stack、Backend；香港搜索；最多 50 个有效职位；正常 600 秒 provider 预算及 525 秒采集窗口。只读观察器记录浏览器导航，不替换查询、响应、读取结果或等待策略。没有用账户登录态，也没有 LLM 调用。

| 阶段 | 北京时间开始 | 总耗时 | 详情尝试 | 完整 JD | 成功率 | 失败原因 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 仅候选筛选 | 2026-10-18 12:30:46 | 134.953 秒 | 32 | 26 | 81.25% | 5 个 410；1 个同 ID 改名误判 |
| 最终实现 | 2026-10-18 12:35:43 | **70.487 秒** | **19** | **11** | **57.89%** | 6 个 404；1 个 410；1 个 403 |

成功率 = 完整 JD 数 / 实际尝试的详情 URL 数。正常去重在尝试前执行。该比例不是全站覆盖率，也不是职位资格通过率；未执行地点、标题等业务筛选，搜索结果可能包含香港之外的职位。

两轮均完成四个逻辑关键词搜索、仅导航真实详情路径，未访问新闻、分类或列表页。第一轮 26 份 JD 长度 1,067–7,941 字符；两轮所有成功 JD 均保留正文与 SHA-256，校验一致。

两轮关键词和配置相同，但 Tavily 实时返回的候选 URL 不同，不能作为严格性能对照。最终实现的最后一个 403 触发原有整来源停止规则，未继续剩余候选。因此结果为 fetched 且 truncated / incomplete_details，较短耗时不能解释为性能提升。最终轮没有 JobPosting 身份错误，但是否覆盖改名样本须看下述独立验证。

另对真实职位 ID `24760865` 做修复后单例验证：请求旧标题 URL，结构化 JD 指向新标题 URL，HTTP 200，**3.896 秒**，成功取得 1,146 字符 JD。该单例不加入上表来源验证的分子或分母。

## 证据与清理

运行目录仅保留六份必要证据：两轮各自的 collected 和 summary，以及修复前后的身份样本观察。summary 包含来源配置、四个查询、耗时、逐次导航 HTTP 状态和源码哈希；collected 保留完整 JD。临时观察逻辑均以内联进程执行，进程已退出，没有留下实验脚本、队列、进度文件或生产调试日志。历史 LinkedIn 证据和无关用户文件未改动。

Verdict: Ship. 非详情页和改名身份误判这两项根因已修复，回归及真实单例通过。

Not checked: 长期限流稳定性；404/410 的搜索索引陈旧和 403 后整来源停止仍限制覆盖，后者保留为下一项独立决策，本次不扩展恢复策略或列表页遍历。
