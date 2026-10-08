# OII-397：三个独立维度 agent 隔离实验（2026-10-08）

公开公司实体、四个 scopes、三个 seed URL 和三个真实微软岗位（6/9/10）经程序完成独立采集、各维度 LLM 摘要、各维度 Jev 评分与持久保存。首次 cold 的 company 摘要失败；修正摘要额度分配后，恢复运行仅复用已采来源重做该摘要及评分。最终四个公司 profiles 均有评分，warm 全链零网络。正式 DB、评分图、cron 和 Dashboard 未切换，未设置充分性推荐阈值。

每个 company/culture/compensation agent 独立拥有 200K token，采集最多 150K，至少留下 50K 给本维度摘要；未用采集额度可流入其摘要。多个薪酬 scope 共用 compensation agent，不按 scope 重置。无公司共享 token 上限，600K 仅为三个独立额度之和。仍保留每 agent 20 保守 Tavily credits、570 秒采集 dispatch 和 900 秒模型期限，CLI 另有 900 秒整体 hard deadline。是否移除 credit 边界尚未确认，本轮未擅改。token 预约是估计，并非 provider 精确用量保障。

三个 agent 各有上下文、tool cache、ledger 和时钟；研究及摘要仅使用公开资料及对应维度 topics，采集终稿不再承担精准引文整理。摘要使用 low reasoning，主流程只合并程序生成 profiles。每维度摘要完成立即独立请求 Jev，compensation 两个 scope 在同一请求内独立评分。失败不阻塞其他维度，也不在聚合阶段隐式重试。实体/scope/JSON 结构边界保留，摘要没有逐字引用或 hash 完整性验收；缓存 fingerprint 用于查找去重，语义正确性仍需审阅。

## 实际资源与失败

| Agent | 采集 reported tokens | 首次摘要 reported tokens | Cold 合计 | 采集停止原因 | 保守 / reported credits |
|---|---:|---:|---:|---|---:|
| company | 116762 | 44946（失败） | 161708 | credit_budget_exhausted | 20 / 12 |
| culture | 107939 | 13632 | 121571 | token_budget_exhausted | 20 / 15 |
| compensation | 103512 | 21272 | 124784 | token_budget_exhausted | 20 / 12 |

17 次采集模型响应全部返回，reported 合计 328213（input 313760、output 14453、cache_read 78592）。首次三个摘要合计 79850，cold 总量 **408063**。首个 company 摘要 input 23952、output 20994 全为 reasoning，触发 LengthFinishReasonError，无有效 JSON，未发 company Jev。初版把摘要预留误作 50K 硬上限，未开放尚未使用的本 agent 额度；已修成 `200000-accounted`。旧 cold 输出还把缺失摘要的公司聚合标成 scored，现已按原请求 scopes 判 partial，历史产物保留。

恢复是一次新的有界 CLI attempt：没有重新研究，没有人工修 JSON；仅 company 摘要新增 **32961** reported tokens（input 24069、output 8892、reasoning 6856）。初次失败与恢复累计 **441024**，不存在把未知预约算成实际 tokens。成功响应输出比旧上限还少，故不把一次重新采样成功归因为增大上限的统计因果。预约 61774 不是实际消费。美元费用未知，cache_read 也不能当作全价重复 input。

| Run | 墙钟秒 | Jev 新 logical requests / HTTP attempts | Jev cache units | 新评分问题数 |
|---|---:|---:|---:|---:|
| cold（部分完成） | 335.77 | 5 / 5 | 0 | 12 |
| recovery（复用采集） | 87.13 | 1 / 1 | 5 | 2 |
| warm（全链复用） | 0.03 | 0 / 0 | 6 | 0 |

Cold culture/compensation 在各自摘要结果落盘后约 0.8 秒开始评分，早于 company 摘要失败结束，验证了独立就绪后评分。恢复的其余两维度及三个 direction 均复用；warm 没有研究或摘要调用。总计 Jev 6 HTTP、14 个评分/Noul 问题，无隐藏第二轮公司评分。

采集墙钟分别约 company 120.66、culture 146.51、compensation 155.55 秒。搜索次数分别 10/14/11，extract 次数 1/5/4。共冻结 24 个 provider 返回正文、236061 字符，16 个超过 4000 字符；按 URL+正文 fingerprint 去重为 22 个，不是 24 个独立网站，也不代表网站全量覆盖。

## 最终原始结果

下表仅显示两位小数，保存响应及程序期望分未取整、截断或修正；充分性是独立 Noul，非覆盖百分比或摘要正确率。

| 单位 / scope | Score | Confidence | Noul |
|---|---:|---:|---:|
| company / global | 4.02 | .67 | .49 |
| culture / China | 3.40 | .34 | .11 |
| compensation / China:Beijing\|Shanghai\|Suzhou，SDE2，CNY annual_total | 4.69 | .75 | .29 |
| compensation / China:Suzhou，SDE2，CNY annual_total | 2.84 | .44 | .09 |
| job 6 / direction | 4.93 | .94 | .79 |
| job 9 / direction | 4.96 | .97 | .85 |
| job 10 / direction | 3.95 | .95 | .74 |

岗位 6/9 引用同一多城薪酬 profile，10 引用苏州 profile；三岗位公司及文化引用一致，保留原 batch request hash。有效期 2026-10-15 仅本轮实验输入，不是正式 TTL 政策。所有推荐仍为 threshold_pending。

## 可观察证据收益与局限

- Company 专项搜索覆盖领导变动、经营及资本投入、本地裁员、股价事件，摘要区分计划与实际投入。仍未取得 seed 所指 FY26 Q4 完整材料及本地官方裁员确认。**摘要错误仍存在**：SCMP 无可确定发布日期，模型却从图片路径推断 2026-06-09，并给 July 6 添 2026 年；不应视为已验证时间事实。本报告审阅不回写模型产物。
- Culture 保留了 2017-04-27 大中华区家庭假期政策日期，以及全球 hybrid 与地区福利限制。但产假、陪产、收养和照护是不同资格待遇，合计“36 周”不能解读为一般员工均有 36 周假。当前中国休息制度、净工时、加班执行、年假病假及险金基数比例仍缺；旧公告不证明当今执行。
- Compensation 已进行奖金、RSU 和归属专项搜索，取得北京 metropolitan 年包 508912 CNY（base 384251、stock 105876、bonus 18785）与 Greater Shanghai 434678（343534/76332/14820）的第三方数字拆分。都市圈不等于单城市辖区，公开基准不是 offer。中国 headline 与 `.md` 有 8 元差异且均值/中位数表述混合。苏州 Levels 空表不证明网站无数据；2023 匿名 SDE 自述职级未知，不能替代 SDE2。因此 2.84/.09 不能证明实际年薪低于个人底线，奖金资格、股权形式及兑现仍未知。

相比此前混合研究，一次运行有更多薪酬定向探索与日期上下文，但来源、prompt 及模型路径均变化；没有随机性控制，不能把分数或 Noul 变化称作可靠性提高。文化和苏州薪酬缺口仍明显，公司日期推断还会出错。三 agent 分工及复用已验证，不代表已可可靠正式推荐。

## 回查与验证

本地完整产物：`data/experiments/company-three-agent-2026-10-08/` 的 `input.json`、`run.py`、`cold/`、`recovery/`、`warm/` 与 `store/microsoft/evidence/`。采集 raw、失败摘要、成功摘要、Jev request/response、scope archives 和 cache 均保留。`run.py` 仅以 HEAD transport 快照保护既存未提交 `jev-score.py` 回退，没有注入事实。初始 manifest 的 summary 50K 记录属于修正前版本，应结合本报告与当前源码理解。

三个 narrow checks（company pipeline、company score、adaptive research）、233 项 syntax check、workflow-scan 及 diff check 通过。离线验收还覆盖新增 scope 只调对应 agent、多个薪酬 scope 共用额度、摘要规则变更复用来源、评分规则变更只重评、JD 变更仅 direction、摘要失败导致整体 partial、Jev 失败不聚合重试与实际 ledger。新 scope 是 mock 验收，本轮真实网络仅上述微软 cold/恢复/warm；助手及 root 独立审阅不充当流程产出或语义金标。
