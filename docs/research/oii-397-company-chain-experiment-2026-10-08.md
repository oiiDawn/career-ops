# OII-397 自动公司采集、摘要、评分与岗位复用试验

2026-10-08。正式数据库、评分图、cron 和 Dashboard 未切换。

公共公司输入现在能由程序完成调研 → 独立 LLM JSON 摘要 → scoped profiles → Jev → 持久档案和岗位引用。此前同类输入被旧 validator 要求手工 `profiles` 拒绝。本轮真实输入只有微软实体、声明范围、三个 seed URLs、显式有效期和真实岗位 JD，没有人工准备的事实或摘要。首次自动采集后摘要失败；后续真实 CLI attempt 自行复用已采来源并重新摘要，最终成功。**这是从空 store 开始、经过有记录失败恢复的完整链验收，并非最终版本一次全新采集即成功的证明。**

按用户最新要求，摘要只检查 JSON 字段和声明的 profile/scope 边界，保留 claim/date/kind/applicability/limitations 和 source URL/ID；不逐字匹配引文、不校验正文 hash/offset 完整性。摘要事实正确性留给低成本审阅。缓存 fingerprint 只用于版本/输入去重，Jev response schema 仍验证。无人工改模型 JSON、代写摘要、raw source 评分 fallback 或自动复核。

## 输入与产物

所有真实输入和原始输出在忽略目录 `data/experiments/company-chain-2026-10-08/`。`input.json` 包含保留岗位 6/9/10；`new-job-input.json` 加入真实岗位 122（Software Engineer II，Windows Cloud Experience，Suzhou）。JD 由只读 SQLite 记录导出，`samples.json` 保留来源信息。公司有效期 `2026-10-15` 仅本轮实验使用，不代表正式 TTL 政策。

公共公司范围是 company/global、culture/China，以及 compensation/SDE2/software_engineering/CNY/annual_total 下的 `China:Beijing|Shanghai|Suzhou` 和 `China:Suzhou`。这是声明的评估范围，不把 China 统计变成单城 offer，也不从岗位内容推定新的职级。

`run.py` 调用实际 `company-score.py` CLI，唯一 transport 替换是使用 Git HEAD 的 Jev `call` 快照，避免覆盖工作区既存的 transport rollback；没有注入任何 prepared evidence。重现入口：

```bash
.venv/bin/python -B data/experiments/company-chain-2026-10-08/run.py <新的输出目录名>
# 名称 new-job 时选择真实新岗位输入；其他名称选择原三岗位输入。
```

关键产物：`store/microsoft/evidence/capture-1/` 保存 provider 正文、实际工具调用、raw messages 和 ledger；`summary-1` 至 `summary-6` 保存各次真实 LLM request/response/失败 completion；`simplified/` 保存成功自动摘要及评分入口输出；`warm/`、`new-job/` 保存复用结果。`summary-references.json` 与评分 `company_profiles` 把岗位指向摘要档案和原评分 batch request。失败历史未覆盖。

## 实测结果

|运行|研究/摘要|新 Jev HTTP|新评分+Noul题|缓存评分单元|耗时|
|---|---|---:|---:|---:|---:|
|首次 cold|自动研究后摘要结构失败|3（仅 direction）|6|0|研究 110.18s + 摘要 92.59s|
|最终 simplified|复用程序冻结的来源，LLM 摘要成功|4|14|0|197.61s|
|warm 同输入|4 scope 全部有效，无研究/摘要|0|0|4|0.023s|
|new-job 加真实 122|公司档案及原岗位全部复用，无研究/摘要|1|2|4|0.799s|

最终摘要生成 4 profiles，分别 8/4/2/2 条 LLM 事实。研究材料部分完成、摘要及评分完整；不能因摘要成功称互联网调研完整。

以下每格为 **原始分 / confidence / 独立 Noul 充分性**，显示两位小数，不修改原始分布或 confidence；完整浮点在 results.json。

|岗位|direction|company global|culture China|compensation|薪资 scope|
|---|---|---|---|---|---|
|6|4.95 / .96 / .79|4.32 / .57 / .39|4.17 / .68 / .19|4.57 / .66 / .15|China:Beijing\|Shanghai\|Suzhou SDE2|
|9|4.98 / .99 / .85|4.32 / .57 / .39|4.17 / .68 / .19|4.57 / .66 / .15|China:Beijing\|Shanghai\|Suzhou SDE2|
|10|3.97 / .97 / .73|4.32 / .57 / .39|4.17 / .68 / .19|4.27 / .62 / .11|China:Suzhou SDE2|
|122（真实新岗位）|4.31 / .72 / .83|4.32 / .57 / .39|4.17 / .68 / .19|4.27 / .62 / .11|China:Suzhou SDE2|

同 scope 所有岗位引用同一个公司 batch request `9dbaebe65481d795f9d6d3f53c17f2fba8bb552eee7abf0eaea08be73e8dc450`。warm/new-job 没有再次采集或摘要。这证明完整链持久复用，不能证明摘要事实均正确或高分足以推荐。所有 recommendation 仍 `threshold_pending`，未选充分性阈值。

摘要明确保留的缺口包括：中国官方休息/净工时/加班制度缺失；年假和病假数字来自第三方员工叙述，官方未确认；险金基数比例缺失；弹性工作宣传不能证明当地执行；无当地正式 SDE2 薪资 band/offer，股权归属、奖金条件和城市拆分仍未知。China-wide 第三方参考不能证明苏州待遇。这些缺口与 culture .19、comp .15/.11 的低充分性一起可见，不能因为分数 4.x 就正式推荐。

## 资源、失败及预算边界

单公司 attempt 共用 150K token 预算：研究最多 100K，所有摘要组共同最多 50K；采集 dispatch 上限 570s，整体 CLI alarm 900s，为摘要留墙钟时间。实例参数不改变独立 Research 默认行为。token 预约用 cl100k_base +20% 代理估计，返回后按 reported usage 记账；不是 provider 精确 tokenizer 或绝对 token hard cap。20 credits 按 URL 保守预约，美元费用未知。每次新的 CLI attempt 有新的预算，开发迭代总量不能冒充单次成本。

真实研究调用 4 LLM、6 search、4 extract、4 read_sections，超过原 search5/extract1 限制；stop 为 `token_budget_exhausted`，保留已经取得的材料。8 个 provider-returned bodies 共 118,300 字符，其中 7 个超过 4000，最大 45,523。保存的是 provider 实际返回全文，不是整个网站或所有 PDF 的完整内容。Tavily reported 8 credits，保守预约 16；没有为摘要恢复再次采集。

|摘要 attempt|参数/结果|reported tokens|
|---|---|---:|
|1|旧严格契约，模型 scope 字符串不符合结构，failed|26,544|
|2|xhigh，LengthFinishReasonError；17,854 output 全为 reasoning，无正文|42,654|
|3|medium，同类长度失败；18,776 output 全 reasoning|43,576|
|4|low，旧引用契约合法摘要；过大 Jev 请求首个 HTTP400，后去重复材料成功|38,715|
|5|误把实验 wrapper 当作支持 --help 使用，触发本地网络失败；无有效 completion usage|未知|
|6|用户简化契约后 low，4合法 profiles；raw JSON 未手改|34,976|

摘要5的 `tokens_accounted=50000` 是失败调用的保守未知预约，**不是已知消费或费用**；`schema-placeholder/` 历史保留。首次严格摘要失败与两次 reasoning 耗尽不是安全拦截。所有失败均持久保存，不用助手补齐阶段。

研究 reported 74,378 tokens，最终摘要 reported 34,976（input 17,166 / output 17,810，其中 reasoning 14,181）；研究加最终摘要合计 109,354。整个开发实验所有有 usage 的 LLM attempts 合计 **260,843**，另有摘要5未知 usage；不能只报成功那次成本。阶段文件时间估计研究加所有有 usage 摘要累计约 940s，分属多个有界 CLI attempts，不是单次 900s 内全部完成。

整个实验 Jev 13 HTTP attempts，12有效响应、1保留 HTTP400；最终版本三岗位 4有效 HTTP（14题），warm 0，真实新岗位 1（2题）。最终三岗位新请求文本共 77,438 字符，新岗位增量 13,336。Jev 未提供可据以核算的实际美元费用或模型 token usage。重跑 direction 的历史也计入总 HTTP，不将失败/调参成本隐藏为 cache 收益。

研究和摘要外发仅公共实体/scope/网页材料，无私人评分标准、薪资底线、CV、联系方式或候选经历；Jev 外发公共材料与已授权标准。局部文件路径只保存在本地档案引用，未送摘要或 Jev 请求。

## 验证与界限

`workflow-company-pipeline-test.py` 验证真实阶段调用链（provider/LLM transport mock）、有效缓存免研究、JD变化只direction、新scope只补缺失范围、摘要规则变化仅重新摘要、评分规则变化仅Jev、有效期刷新、无效JSON不评分、未知profile ID拒绝。旧精准引文/hash测试已删。另有 `workflow-company-score-test.py`、`workflow-adaptive-research-test.py`、233个 MJS syntax check、`workflow-scan-test.py` 和 `git diff --check` 全通过。

本轮修复的是自动阶段衔接及持久复用，事实可信度、充分性验收和正式接入仍需审阅。助手独立检查不是流程产出阶段，也不是语义金标。真实研究部分停止、低充分性和所有失败保留，不承诺查全，不自动纠正 Jev 分数。
