# LinkedIn 正式 discovery 验收（2026-10-18）

## 范围与审查

使用修复后的原链路运行真实 discovery，正常过滤、去重并写入 `data/opportunities.db`。不使用 jev-ultrafast，不修改资格规则、模型配置或总耗时预算。后续范围按用户最终选择：完成本次全部新增职位的资格初筛，评分交给常规队列。

[ponytail 审查](linkedin-ponytail-review-2026-10-18.md)发现并修复三处根因：尊重超过本地等待上限的 Retry-After（跳过当前请求，不提前重试）、复用严格职位身份解析、删除会被上层误记为失败的正常重试日志。保留同一个固定 deadline、最多两次重试及其他队列项。修复提交 `f591f984`，未新增依赖或通用重试框架。

验证通过：provider 回归、浏览器 hydration 回归、Node 语法检查以及业务 workflow-scan 测试。正式运行采用的源码哈希另存，未以测试替代实际业务验收。

## 正式采集与入库

命令：`.venv/bin/python -B -m career_ops discover --company LinkedIn`。

运行 ID：`3f7713ee238949778c654c61208351f9`。

UTC 开始 `2026-10-18T02:38:00.158616+00:00`，结束 `2026-10-18T02:46:46.351493+00:00`，耗时 **526.193 秒（8 分 46 秒）**，退出码 0。

采用真实配置：中国大陆、香港两个来源；每个来源搜索 AI、AI Agent、Full Stack、Backend 四个关键词；每来源最多 100 个有效结果，每关键词最多 10 页。使用匿名 headless 浏览器、共享 2 秒导航间隔及原有 URL 安全检查。来源采集窗口 525 秒，在 600 秒 provider 总预算中预留 75 秒。

| 结果 | 数量 |
| --- | ---: |
| 有效职位 | 128（大陆 59，香港 69） |
| 正常去重 | 26 |
| 标题过滤 | 55 |
| 地点过滤 | 6 |
| 层级过滤 | 1 |
| 新增入库 | **40，ID 493–532** |

核算：128 = 26 + 55 + 6 + 1 + 40。去重包含既有记录或本轮重复，不能全部解释为既有职位。

结果为 `partial`：两个来源均取得有效职位，但各自在最后的详情请求遇到搜索时间预算截止。原始采集记录有两条最终警告；上层四条 errors 包含两条 stderr 覆盖警告和两条来源覆盖不完整标记。没有最终未恢复的 HTTP 429 警告；正常重试不再输出 stderr，因此不能据此断言运行期间从未发生瞬时 429。此处“全量”指按正常配置执行全部来源和关键词，并不代表穷尽 LinkedIn 全站。

40 个新职位均有不少于 200 字符的 JD 留存，正文 SHA-256 与 capture 的 content_hash 一致。入库后数据库 quick_check 为 ok，foreign_key_check 无违规。

## 初筛执行与评分交接

最初按完整 evaluate 启动，之后用户明确选择只完成资格初筛。范围切换前已有 5 个职位完成了手动完整评分；此后不再主动启动新评分。500 的耗时评分任务通过正常 task cancel 交还常规队列，保留检查点；之后已观察到常规队列正常完成该职位评分并继续处理其他职位。

初筛仅调用现有 task start scan / task resume / task run，使用正常输入、检查点、预算和结果持久化路径。没有直接 SQL 修改业务数据。

早期并行启动过多 CLI 是本轮编排失误，触发 API Key 并发额度及数据库初始化索引竞争。随后停止并行分发，以串行 CLI 恢复未完成初筛，没有为提高通过率修改规则。

数据库竞争来自每次 BusinessStore 初始化执行 DROP INDEX / CREATE UNIQUE INDEX，多个连接交错时出现 `index one_active_task_per_opportunity already exists`。这是独立的并发初始化问题，本轮未修改数据库实现；本次改为串行编排，不能据此认为多 CLI 并发已修复。

最终初筛结果及逐职位清单见下节。后续整体墙钟时间包含早期完整评分、API 失败和恢复，不能当作纯初筛性能基准。

## 留存证据

- 正式运行、输入、时间、源码哈希和新职位清单：`data/cache/linkedin-production-20261018/`。
- 不可变采集与过滤决策：`data/cache/configured-discovery/3f7713ee238949778c654c61208351f9/{collected.json,decision.json}`。
- 初筛原始 CLI 输出：运行目录下 `prescreen/` 和 `prescreen-serial/`；错误、取消及恢复过程均保留，不把失败尝试算成成功结果。

没有提交申请或向外发送消息。

## 最终验收

初筛在 UTC `2026-10-18T03:53:08.594384+00:00` 全部完成：**40/40，30 个通过，10 个排除，0 个遗留等待项**。通过率 75%；这是资格初筛结果，不代表岗位适合度评分或录用概率。

从首次 evaluate 启动到全部初筛完成约 65.4 分钟，其中包含此前完整评分和并发失败恢复；串行恢复阶段 43.0 分钟，也包含等待此前任务结束，均不作为纯初筛性能基准。

排除证据标签（可重叠）：经验年限差距 8 个，多个核心能力缺口 5 个，薪酬门槛 1 个，共对应 10 个排除职位。每项详细证据保留在业务结果和 `final-verification.json`。

在 `2026-10-18T03:53:29.638539+00:00` 核验：数据库共 458 个职位；quick_check 为 ok，外键违规 0，活动任务索引存在；40 份 JD 正文哈希全部一致；正式源码哈希未变化；没有活动 scan 任务。已完成的 8 份评分报告文件哈希也全部一致。

评分交接快照：30 个初筛通过者中，8 个已有评分，22 个待常规队列处理（包含一个正在评分的 505）。已有评分包括范围切换前手动完成的 5 个和之后由常规队列完成的 3 个。本轮不再手动推动其余评分。队列会继续变化，此处仅为验收时间快照。

| ID | 公司 | 职位 | 资格初筛 | 排除证据标签 |
| --- | --- | --- | --- | --- |
| 493 | Outepai | Senior AI Engineer | 排除 | years_gap_terminal |
| 494 | 友邦科技 | Senior Full Stack Software Engineer-AI | 排除 | years_gap_terminal |
| 495 | 平安健康保险股份有限公司 | 09715N-大模型算法工程师 | 通过 | — |
| 496 | Beijing Memblaze Technology Co., Ltd | Web全栈开发工程师(J10152) | 通过 | — |
| 497 | 牧原食品股份有限公司 | 后端开发工程师 | 通过 | — |
| 498 | Sailglobal | Sailglobal AI \| Full Stack Engineer | 通过 | — |
| 499 | 拜耳 | Artificial Intelligence Engineer | 通过 | — |
| 500 | 重庆美心集团 | 软件工程师 | 通过 | — |
| 501 | 英伟达 | Senior Software Engineer, Humanoid Robotics | 排除 | multiple_core_capability_gaps |
| 502 | 拼多多 | ai agent 算法工程 | 通过 | — |
| 503 | 德科集团 | Full stack developer (AI Project) \| 45K | 排除 | compensation_failed, years_gap_terminal |
| 504 | Argyle Hotels Group | 后端开发工程师 | 通过 | — |
| 505 | 沃尔玛(中国)投资有限公司 | 高级AI平台/应用开发工程师 | 通过 | — |
| 506 | 高博医疗集团 GoBroad Healthcare Group | 全栈开发工程师 | 通过 | — |
| 507 | Duolingo | Senior Software Engineer, Backend, Monetization | 通过 | — |
| 508 | 科睿驰(北京)医疗科技发展有限公司 | 全栈工程师 | 排除 | years_gap_terminal, multiple_core_capability_gaps |
| 509 | 维塔士 | Senior Machine Learning Engineer | 排除 | multiple_core_capability_gaps |
| 510 | AVEVA | AI Application Senior Technologist | 通过 | — |
| 511 | 上海建科工程咨询有限公司 | 全栈工程师 | 通过 | — |
| 512 | 西门子 | AI Native 后端工程师（企业级 AI Agent 开发平台） | 通过 | — |
| 513 | 赛默飞世尔科技 | Software Engineer | 通过 | — |
| 514 | HYPEBEAST | Senior Software Engineer | 排除 | years_gap_terminal |
| 515 | Sailglobal | Sailglobal AI \| AI Engineer | 通过 | — |
| 516 | 上海真兰仪表科技股份有限公司 | 软件工程师 | 通过 | — |
| 517 | Binance | Pioneer Talent Program - Applied AI Agent/AI Productivity Engineer (Top Talent Program) | 通过 | — |
| 518 | Firework | Sr. Backend Software Engineer | 通过 | — |
| 519 | Binance | AI Agent Engineer | 通过 | — |
| 520 | Binance | Pioneer Talent Program - Full Stack Engineer (Front-end Oriented, APAC Remote) | 通过 | — |
| 521 | Not Another Headhunting Company | Senior Full-Stack Engineer (Go) | 排除 | years_gap_terminal, multiple_core_capability_gaps |
| 522 | Capco | AI Engineer \| Insurance | 通过 | — |
| 523 | Tenth Revolution Group | Backend Engineer / Senior Backend Engineer (Go) | 通过 | — |
| 524 | Harper | Forward Deployed Engineer, Hong Kong (3+ yrs) at a $5B AI Unicorn | 排除 | years_gap_terminal |
| 525 | TOPPAN Security | Full-Stack Developer | 通过 | — |
| 526 | Citadel Securities | Full Stack Software Engineer | 通过 | — |
| 527 | Binance | Pioneer Talent Program - Full Stack Engineer (Back-end Oriented, APAC Remote) | 通过 | — |
| 528 | Capco | AI Engineer \| Financial Services | 通过 | — |
| 529 | AIA Hong Kong and Macau | AI Application Data Science, Consultant | 通过 | — |
| 530 | Chubb Life | Chubb Life HK - Full Stack Engineer | 排除 | years_gap_terminal, multiple_core_capability_gaps |
| 531 | Ambition | AI Engineering - Team Lead \| Hong Kong | 通过 | — |
| 532 | BAH Partners | NEW: Python Software Engineers Wanted! \| Tier-One Trading &amp; Buy-Side Firms \| Hong Kong &amp; Shanghai | 通过 | — |

未检查：长期限流稳定性和多主机并发。剩余风险：本次两个来源都达到采集预算，覆盖不完整；独立的数据库并发初始化竞争仍未修复。
