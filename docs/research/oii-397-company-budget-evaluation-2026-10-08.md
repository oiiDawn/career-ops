# OII-397 LLM 自主公司探索预算对照

2026-10-08。一次有界冷采集扩容，正式代码、标准、DB、cron 均未修改。

结论：100K 采集预算确实限制后续轮次，但单独翻倍没有解决主要瓶颈。扩容取得中国 Azure 裁员影响、员工福利更多细节；适用的奖金、股权归属及城市薪资证据仍不足。两次都 token-budget stop，扩容研究 96.0% reported tokens 为输入。优先改善历史上下文消耗、维度 topic 探索、来源日期保留及错地区材料过滤，再决定默认预算；这是一家公司一次随机路径对照，不是受控重复或因果 A/B。

## 入口与边界

ignored 实验目录 `data/experiments/company-budget-2026-10-08/` 保存 `input.json`、`manifest.json`、`acceptance-topics.json`、`run.py`、provider/messages/body/ledger、真实摘要和程序生成的 `prepared.json`。输入公共微软实体、4 scopes、3 seed URLs 与此前 company-chain 实验相同，无岗位/CV/私人偏好发给研究模型。model/env 和研究/摘要 prompt 未变。历史 baseline 是 `data/experiments/company-chain-2026-10-08/store/microsoft/evidence/capture-1/` 与最终 `summary-6/`，不是历史全部开发失败成本。

短 harness 调用现 Research.run → retrieved_evidence → summary_sources → summarize_company，合法 JSON 自动生成 profiles，无人工事实/选段/摘要插入。只在独立实验进程将保守 credit 额度设为40；未修改源码常量。研究200K、摘要50K，整 attempt250K/900s，采集570s；摘要 low，采集原配置不变。仅一次采集和一次摘要，没有失败调参重试。全文是 provider-returned 正文，不承诺整个网站/动态表格内容完整。

原计划末端调用 Jev；自动审批两次拒绝私人薪资 floor/target rubric 发往 Typesafe，因为本子会话的 trusted user transcript 无法核实明确授权（第二次虽提供父会话的逐字授权，仍被审查视为 justification 自述）。安全替代完成 public-only 研究/摘要；**没有发送任何 Jev 请求**，不绕过、不再尝试。本轮评分/confidence/Noul 变化因此未知，不能将摘要或 topic 数当评分代用品。拒绝记录在 `score-approval-rejection.json`；公共阶段完成、评分 pending。

## 资源与停止

|指标|baseline|扩容|
|---|---:|---:|
|采集 token allowance|100,000|200,000|
|保守 Tavily credit allowance|20|40|
|采集实际 reported tokens|74,378|162,440|
|输入 / 输出|69,671 / 4,707|155,956 / 6,484|
|cache_read / reasoning|37,888 / 3,259|65,536 / 4,321|
|输入占全部 reported tokens|93.7%|96.0%|
|LLM / search / extract / read|4 / 6 / 4 / 4|8 / 6 / 7 / 6|
|保守 credits / provider reported|16 / 8|24 / 9|
|采集 wall|110.18s|235.07s|
|stop|token_budget_exhausted|token_budget_exhausted|
|冻结 body数 / 字符|8 / 118,300|13 / 209,790|
|摘要 reported tokens|34,976|37,384|
|采集+摘要 reported tokens|109,354|199,824|

扩容摘要 input16,939/output20,445，其中 reasoning16,976、cache_read0；208.24s。公共完整链443.32s，摘要合法4 profiles（facts7/3/3/3）。研究不是 output reasoning 耗尽：研究输出只有6484，4321 reasoning；增长主要来自反复携带历史。8轮输入为1728→12521→14662→16752→22224→25878→29319→32872。累计输入含重复 history，无法据此精确划分每段冗余；cache_read不能按全价重复输入计算。未缓存输入由31,783增至90,420（2.84倍），不等于实际账单。美元费用未知。

达到 token stop 时尚有 nominal 37,560 tokens 余量，但请求前输入估计及最低输出预约无法支付下一轮。token估计沿用cl100k_base+20%，是代理估计，不是精确provider tokenizer或绝对hardtoken保障。900s墙钟和credits界限未触发；credits扩容并非此次限制原因。9个body超过4000字符，最大45,523；正文数/总字符包含菜单或空表，不等于业务有效证据量。

## 自主路径与适用证据

扩容6个真实 query：公司中国研发人数；“微软 苏州 研发 薪资 工程师 年薪 五险一金 公积金”；中国 Azure 裁员；员工年假病假/弹性；2017family leave；苏州公积金12%/全额。baseline6query无薪酬专项；本次虽有综合薪酬query，仍无奖金绩效/RSU grant/vesting/payout专项探索。不能把未定向探索归为公开信息不存在。

|topic|baseline|扩容实际情况|
|---|---|---|
|持续经营|FY26全球财务正文|相同官方财务支持；未增加中国营收/人数|
|持续工程投入|FY26已完成capex；计划缺口|相同来源整理了R&D金额和capex；没有新增未来计划依据|
|裁员/收缩本地影响|全球裁员，地方影响未知|取得SCMP部分正文：中国Azure北京/上海200–400人、第三轮/两年、severance/Canada；TNW是同源二手转述并提其他团队未受影响，不是独立双源|
|领导调整/股价事件|未专题探索|未专题探索；不宣称已经查齐|
|rest/netH/OT|宣传/员工工作叙述，净工时未知|脉脉无固定时间/反对常加班单一员工叙述；没有可计算净工时、rest或OT政策|
|年假病假|第三方15年假/15病假|脉脉15入职年假、>5年递增封顶20、3volunteer/15sick/20caregiver/6周陪产；疫情额外5日不是当前普遍20日政策，当前官方执行未证实|
|弹性/管理|旧官方宣传与员工叙述|脉脉remote/输出导向manager经验；单团队、匿名、COVID时期，代表性未知|
|几险几金基数比例|缺失|脉脉full五险一金及配偶子女商业险；具体基数/比例仍未知，full不能证明基数就是实际工资|
|culture执行/日期|部分source头日期漏入摘要|新脉脉保留COVID时期而非冒称当下；精确发布日期仍未知。新加坡2017官方页有日期但错地区且假期数字未从image提取；China官方页404|
|region/grade annual组成|China SDE II参考，非单城offer|相同Levels China aggregate；HTML482378与.md482386差8元明确列conflict，base/annualizedstock/bonus没有新的当地验证|
|保证/浮动|没有适用policy|仍缺失；美国USDguide不能证明中国保证或浮动|
|奖金绩效条件|未专题探索/缺失|无专项query；Sina美国guide的0–20%不是中国证据|
|股权授予/归属/兑现|annualized benchmark，制度缺口|仍缺vesting/payout；脉脉股票9折是购股福利，不是RSU授予条款；美国guide错scope|
|单城适用性|China aggregate非苏州|京沪苏3个URL正文只有空Salary Data/Latest Submissions表头，无数字；苏州.md提取失败，不能以空提取证明实际网站没有数据|

已记录5个失败URL：Levels北京区域页、招聘平台评价、Jobui salary均访问失败；China family官方页404；Suzhou.md失败。Rivermate China guide仅链接目录；新加坡family leave错地区；Sina虽有完整美国USD salary/stock/bonus guide，不是中国SDE2适用证据。没有因为网页多或题数多就算覆盖改善。

## 摘要错误与剩余缺口

助手独立来源审阅发现，摘要把SCMP/TNW July6自动写成2026；已取得正文没有确定 publication date 或年份，不能从image URL推。这是摘要错误，不是预算不足。摘要把城市提取空表称“没有submissions/没有city estimate”，也过强：动态数据提取不全与数据实际不存在不同。美国薪资guide虽然带limitations，仍进入两个中国comp profiles，不应在以后评分当适用benchmark。没有手改模型产物或正式档案。

baseline的PingWest正文头2020-10-11、Microsoft newsroom头2015-04-28已经采到，却在摘要标undated，属于选段/摘要丢日期，不是资料不存在或预算不足。扩容未重取这两页，不能宣称修好了日期链；新加坡2017头日期虽保留，却错地区，不能当中国culture提升。

本轮确有地方经营风险和福利细节收益，但公司local facts还需年份核实，culture仍缺当前官方制度、净工时及险金比例，comp核心适用缺口基本不变。下一步优先短history、topic缺口定向探索、保留source日期、隔离wrongscope；之后用重复对照决定是否扩大默认额度。Noul不是coverage百分比或摘要正确率，本轮无新Noul。正式生产和默认预算保持不变。

本轮仅新增ignored harness和本报告；`git diff --check`通过。既有jev rollback与upstream文档未改、未提交；未push。
