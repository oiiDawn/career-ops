# OII-397 正式评分接入与验收（2026-10-08）

正式 `task start score` 已接入三个独立公司维度 agent，各自完成公开调研与摘要，再独立请求 Jev、立即保存公司评分；岗位只另评 direction。源正文、失败、摘要和请求响应保留，未由助手填补流程结果。Dashboard 与报告显示四维原始小数、confidence、独立 Noul 和适用 scope。充分性阈值未决定，结果为 evidence_review，不自动推荐或通知。

## 实际结果

使用保留的真实微软 JD：6（Work IQ）和 9（UIPilot），不是新抓取的岗位存活验收。最终完整正式结果是岗位 9；数据库 evaluations、results、三个公司评分和三个岗位引用一致。

| 维度 | Score（显示两位小数） | Confidence | Noul |
|---|---:|---:|---:|
| direction | 4.97 | 0.98 | 0.85 |
| company | 4.07 | 0.66 | 0.40 |
| culture | 3.86 | 0.56 | 0.17 |
| compensation | 4.29 | 0.68 | 0.16 |

公司 global、文化 China、薪酬 China:Beijing\|Shanghai\|Suzhou / Software Engineer 2 / CNY / annual_total 分别维护。文化和薪酬数值不代表已确认当地实际净工时、险金基数、奖金资格或个人 offer。公开薪酬基准不能替代 offer；低充分性仍需审阅，公司新闻日期也不能仅因摘要给出日期就视为验证过。

## 实际成本与恢复

| 正式任务 | 状态 | 累计运行秒 | 混合调用计数 |
|---|---|---:|---:|
| 岗位 6 初次 | 报告输出截断后取消，原始记录保留 | 562.15 | 63 |
| 岗位 6 修复后 | 完成，company pending | 762.81 | 30 |
| 岗位 9 首次及恢复 | 完成四维 | 434.96 | 7 |

混合计数包括 LLM、研究工具与 Jev，不是 LLM 请求数。保留 ledger 中共 27 次研究模型响应、14 次摘要模型尝试、35 次搜索、10 次 extract、9 次 read_sections。研究+摘要 reported tokens 合计 **669751**，其中包含失败、重试和规则调整。它不包括 scope_plan、报告正文 LLM 的 tokens，不是完整美元账单；美元费用未取得。Tavily reported credits 合计 40。

三项当前有效档案对应的研究+成功摘要成本为 company 113816、culture 133447、compensation 138237 tokens，合计 **385500**。这是分阶段实际记录的组合，不是一次无故障冷启动 benchmark。其余费用来自首次摘要失败、旧摘要及薪酬 currency scope 的修正。不能把这次迁移试验声称为成本或准确性已实现同比提升。

实际修复三处：摘要及报告沿用模型已有单次 32768 输出上限，摘要仍受本 agent 剩余 200K 预算限制；支持合并事实的多个来源 ID；独立 SQLite 连接保存维度评分，避免并发重复初始化索引。company 修复后的摘要 36073 tokens。单次输出上限和累计预算是不同约束。

岗位 9 恢复阶段 **0 次研究、0 次摘要、3 项公司评分缓存命中，仅 1 次 direction Jev 和 1 次报告 LLM**；这段耗时 178.93 秒，说明报告生成仍有明显延迟。相同输入再次调用返回同一 completed task，新增调用为 0。全新岗位的 scope_plan 与报告仍需 LLM；不能宣称新岗位零 LLM。三个公司评分已在岗位报告发布前跨连接可见，见独立保存快照。

岗位 6 的部分完成报告作为真实历史保留，未手工补分；公司档案已有完整评分。当前相同 completed 输入按既有任务幂等规则复用，不自动改写这份历史报告。

## 预算与验证

每个 agent 独立 200K：研究最多 150K，为所有摘要至少预留 50K，未用研究额度可用于摘要；批次、合并、单次 JSON/截断修复与传输重试计入该次 agent 额度。三个维度无共享 token 总上限。仍保留每 agent 20 Tavily 保守 credits 与正式 attempt 的 900 秒边界；没有暗中放开这些未确认边界。有效期至本周日 2026-10-11，下一周期输入失效后重建。

formal-score、summary-budget、company-pipeline、company-score、Jev、report、CLI/recovery、模型适配/恢复与 Dashboard 检查通过；233 项 Node syntax 和 workflow-scan 通过。离线检查覆盖冷启动四请求、公司复用、断点恢复、并发锁、多个来源与立即保存。真实正式 CLI 验证发布、SQLite 引用、缓存阶段和同输入零调用复用。

全部验收记录：`data/verification/oii-397-formal-2026-10-08/verified.json`；数据库备份 before.db；独立保存快照 independent-persistence.json；正式源档案 data/company-profiles。Jev 仅收到已授权评分标准（含薪资目标/底线）及公开 JD/公司材料，没有收到 CV、姓名、联系方式或候选经历。配置 LLM 的岗位报告仍使用既有候选事实源，不是 Jev 数据发送范围。
