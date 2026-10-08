# OII-397：公司共享评分的隔离试验

七个真实保留岗位、两个公司实体的固定来源对照完成。三个非 direction 维度按公司与精确适用范围维护，direction 仍逐岗位评分。同输入再次运行没有新增网络调用；只改 JD 的受控探针只新增 direction 评分。**缓存复用有效，但证据充分性没有因此解决，正式评分、DB、cron、Dashboard 与充分性阈值均未切换。**

固定来源对照使用 Jev `jev-1.13.0` 和同一 [四维标准](../../rules/evaluation/four-dimension.md)，冻结 SHA256 `2a9026e28da3ddd09a558947be5e33011351998ca59b03cff55a919e6712a74d`。Score 原生 0–4 加 1，小数、原始 confidence 与独立 Noul 保留；仅下表显示两位小数，不取整、封顶或加总。用户接受近似锚点，微小分档偏移不作阻塞。

## 样本与适用范围

主样本为 Microsoft 4/6/9/10、NVIDIA 23/121；Microsoft 13 是同公司真实香港岗位的跨区边界样本，仍保持原有 ineligible 状态。本轮没有创建新真实岗位或修改业务事实。

- 公司身份显式链接 `microsoft` → Microsoft 官方域名，`nvidia` → NVIDIA 官方域名；SQLite 当前用公司文本，无公司实体表，不靠模糊品牌归并。
- company 维护 global；culture 维护 China，不能借给香港 13。global 公司经营资料不保证当地团队预算或岗位安全。
- MS 6/9 的 Engineer2/II 标题对应本次 SDE2 参考范围，不推内部 61/62 数字职级；多城 `China:Beijing|Shanghai|Suzhou` 保留实际城市未选定，北京/上海底线 350K、苏州 300K，不取单一确定底线。MS 10 单独苏州范围，用 300K 底线。中国薪资参考没有城市拆分，非 offer 或保证金额。
- MS 4 明确 Senior，不能借 SDE2；NV 23/121 只有 Senior/经验信息，IC 未知，不推断 IC2/3/4。NV 北京 IC2/3/4 档案作为明确分级的公司参考独立维护，本轮没有岗位匹配，额外付出三组 Score/Noul，不能作为已确认岗位薪资。
- 香港 13 不借中国文化、CNY 年包或大陆底线，香港保证 base 的 comp 保持 pending。移除了本轮无人引用的微软泛 China comp 档案。
- `valid_until=2026-10-15` 仅为本轮 fixture，不是正式 TTL 决策。

## 固定来源和可追溯性

共享与 per-job 基线都使用相同公共来源 registry、同岗位 JD 和同 scope 事实；不含 CV、旧分数、姓名、联系方式或候选经历。公司评分请求不含任何 JD。基线在每个岗位请求中重复公共公司证据；共享请求只在公司请求中发一次 registry，以精确 source_refs 限定各 profile 的适用材料。请求目标从逐岗位判断变为公司 scope 基线，不能把数值变化归结为新增证据、准确率改善或用户金标。

复用先前 `jev-evidence-gaps.../corrected/sources.json` 的公开摘录和 adaptive 已实际读取的正文范围，没有为固定源对照新联网采集。MS 使用集团财务/R&D、全球和中国裁员、全球福利、STCA 转载及中国 SDE II 员工薪资；NV 使用集团财务/R&D/中国出口风险、全球福利/RSU、地域混合的员工工时报告及北京 IC 表。STCA 摘录排除招聘岗位清单；MS SDE II 薪资排除不相关职级表。保留来源限制，不把官方承诺、法定最低与执行情况合并。

共 16 个不同公共来源记录（IC 分级选段不同，非独立网站数）。助手复核实际源 hash、所有选段 `text == body[start:end]` 及相同 registry/同 JD 通过；这仅验证出处与输入一致，**不是语义金标**。原始来源和旧岗位采证关联在本地 manifest 保留，发往 Typesafe 的证据无旧 job_id、本地路径或 candidate_sources。

## 实际调用与复用

| 阶段 | 新逻辑请求 / 缓存 | HTTP attempts | 新 Score / Noul 题 | 本轮序列化请求字符总量¹ | 耗时秒 |
| --- | --- | ---: | --- | ---: | ---: |
| 同源 per-job 基线 | 7 / 0 | 7 | 28 / 28 | 255,419 | 6.17 |
| shared cold | 9 / 0 | 9 | 16 / 16 | 157,580 | 7.08 |
| shared warm | 0 / 9 | 0 | 0 / 0 | 0 外发（157,580 本地重建） | 0.012 |
| 仅 JD 改变的受控单岗增量 | 1 / 2 | 1 | 1 / 1 | 9,634 外发² | 0.777 |

¹ 字符数是保留请求的 JSON 字符长度，包括标准；不是 tokens、字节数或费用。首次共享 HTTP 9 次多于基线 7 次，不能声称首次减少 API 次数。评分题数 56→32，减少 42.86%；请求字符减少 38.31%，但本次单批共享墙钟略高于基线，不能推广为延迟优势。Jev 未返回可计价 token/费用信息，美元成本未知。

² 受控探针明确为假设维护 C# CRUD 的 JD，不是新真实岗位；公司证据和 scope 不变，两公司请求命中缓存，一次新的 direction 请求。输出目录还保留两个缓存公司请求的逻辑记录，不能将重建总量 81,989 全算网络传输。离线公司证据改变使 request hash 改变；过期公司档案使岗位三维全部 pending；香港文化和 Senior/未知 IC 的薪资 no-match 均通过，不为这些离线验证增加 API。

此前普通沙箱有 18 次本地 DNS `gaierror`（9 单元各两次），没有取得服务响应，另存 `cold-local-network-failure/`，不称 Jev 服务失败或计入成功 HTTP。获准网络访问后 cold9、baseline7、JD probe1，共17 HTTP 全有效。原始请求、每次响应、失败编号与 history 均保留，没有改工作区既存 Jev rollback。

## 七岗同源结果

每格为 **分数 / 原始 confidence / 独立充分性**。共享 pending 不是低分，也不是相对旧数值的得分提升或下降。旧 per-job 模型即使知道范围缺失仍可能输出薪资数字；这些数字不能反证职级或地区适用。

| 岗位 | 维度 | per-job 基线 | scoped shared |
| --- | --- | --- | --- |
| microsoft 4 | direction | 4.94 / 0.96 / 0.84 | 4.96 / 0.97 / 0.82 |
| microsoft 4 | company | 3.61 / 0.49 / 0.37 | 4.18 / 0.60 / 0.37 |
| microsoft 4 | culture | 3.38 / 0.38 / 0.13 | 3.05 / 0.42 / 0.12 |
| microsoft 4 | compensation | 4.32 / 0.43 / 0.09 | pending |
| microsoft 6 | direction | 4.93 / 0.95 / 0.83 | 4.95 / 0.97 / 0.80 |
| microsoft 6 | company | 3.59 / 0.50 / 0.38 | 4.18 / 0.60 / 0.37 |
| microsoft 6 | culture | 3.41 / 0.43 / 0.13 | 3.05 / 0.42 / 0.12 |
| microsoft 6 | compensation | 4.76 / 0.77 / 0.19 | 4.36 / 0.47 / 0.19 |
| microsoft 9 | direction | 4.97 / 0.98 / 0.88 | 4.98 / 0.98 / 0.85 |
| microsoft 9 | company | 3.76 / 0.57 / 0.39 | 4.18 / 0.60 / 0.37 |
| microsoft 9 | culture | 3.51 / 0.48 / 0.13 | 3.05 / 0.42 / 0.12 |
| microsoft 9 | compensation | 4.78 / 0.81 / 0.19 | 4.36 / 0.47 / 0.19 |
| microsoft 10 | direction | 3.97 / 0.97 / 0.74 | 3.96 / 0.97 / 0.73 |
| microsoft 10 | company | 3.68 / 0.51 / 0.42 | 4.18 / 0.60 / 0.37 |
| microsoft 10 | culture | 3.40 / 0.39 / 0.13 | 3.05 / 0.42 / 0.12 |
| microsoft 10 | compensation | 4.72 / 0.75 / 0.21 | 4.27 / 0.38 / 0.18 |
| nvidia 23 | direction | 3.17 / 0.61 / 0.75 | 3.09 / 0.64 / 0.78 |
| nvidia 23 | company | 4.20 / 0.58 / 0.38 | 4.09 / 0.55 / 0.36 |
| nvidia 23 | culture | 2.00 / 0.73 / 0.15 | 1.92 / 0.65 / 0.17 |
| nvidia 23 | compensation | 3.61 / 0.33 / 0.07 | pending |
| nvidia 121 | direction | 3.99 / 0.99 / 0.85 | 3.99 / 0.99 / 0.83 |
| nvidia 121 | company | 4.09 / 0.63 / 0.37 | 4.09 / 0.55 / 0.36 |
| nvidia 121 | culture | 2.03 / 0.68 / 0.15 | 1.92 / 0.65 / 0.17 |
| nvidia 121 | compensation | 4.26 / 0.51 / 0.14 | pending |
| microsoft 13 | direction | 1.83 / 0.62 / 0.64 | 1.92 / 0.69 / 0.67 |
| microsoft 13 | company | 3.79 / 0.58 / 0.42 | 4.18 / 0.60 / 0.37 |
| microsoft 13 | culture | 3.17 / 0.37 / 0.10 | pending |
| microsoft 13 | compensation | 1.79 / 0.32 / 0.05 | pending |

同公司精确范围的 company/culture 数值不再因 JD 改变：微软 company 基线逐岗 3.59–3.79，而共享均 4.18；微软中国 culture 逐岗 3.38–3.51，而共享均 3.05。它们是同一保存结果的复用，不是多次模型一致性测试，也不证明共享数字更正确。MS 6/9 comp 共用同 profile，10 的苏州 scope 单独保存；4/23/121/13 薪资与13 culture 为明确 no-match pending。

公司档案全部原始结果（NV IC 档案不分配给未知 IC 岗位）：

| 公司 | 维度 | scope | 分数 / confidence / Noul |
| --- | --- | --- | --- |
| microsoft | company | global | 4.18 / 0.60 / 0.37 |
| microsoft | culture | China | 3.05 / 0.42 / 0.12 |
| microsoft | compensation | China:Beijing\|Shanghai\|Suzhou / SDE2 | 4.36 / 0.47 / 0.19 |
| microsoft | compensation | China:Suzhou / SDE2 | 4.27 / 0.38 / 0.18 |
| nvidia | company | global | 4.09 / 0.55 / 0.36 |
| nvidia | culture | China | 1.92 / 0.65 / 0.17 |
| nvidia | compensation | China:Beijing / IC2 | 4.37 / 0.49 / 0.34 |
| nvidia | compensation | China:Beijing / IC3 | 4.24 / 0.38 / 0.36 |
| nvidia | compensation | China:Beijing / IC4 | 4.64 / 0.69 / 0.35 |

NV 同北京、同 CNY 年包来源的 IC2 参考531K、IC3参考621K，均高于400K目标锚点，但原始分4.37→4.24；年薪上升却评分下降，不能称近似锚点趋势全符合。这是 Jev 数值校准与范围判断待审阅的问题，不是 cache bug；保留 raw，不自动修分或追加调用。

助手证据审阅仍发现：公司集团经营/R&D 事实有用，但地方岗位连续性不能直接证明；culture 的净工时、当前休息安排、社保/公积金基数比例及实际执行仍缺，中国 STCA 转载与混合地域员工报告也不能覆盖全部团队；薪资只有员工参考或公司制度，未知职级、多城市、奖金适用金额与股权兑现条件仍限制具体岗位判断。MS culture Noul .12、NV .17；MS 匹配薪资 .18–.19；即使 NV IC 参考 .34–.36，也非 offer 充分性验收。没有选择新充分性阈值、自动复核、fallback、focus 或正式推荐。

## 独立公司研究 smoke

一次 MS `--company-input` 研究已结束，`research_unit=company`，无逐岗位输入。使用当前 `deepseek-v4.1-flash`/`xhigh`，约147.33秒，5次模型调用实际报回134,004 tokens、9 search/4 extract/4本地回读；网络保守额度20、provider报回11 credits。11份完整 provider 返回 body 合计210,696字符，10份超过4000，最大45,523；79个实际已读范围经助手本地hash/offset回查通过。它不证明整个网站完整，导航噪声、重复以及地域不适用仍存在。

**该 smoke 为 partial：下一次模型token预约无法在150K资源预算内支付，停止为 token_budget_exhausted，没有有效最终JSON/facts；不补摘要调用。** 原始全文/已读材料完整保存但未混入固定源评分，不据采到更多材料声称质量提升。取得公司财务、大中华区/苏州招聘介绍、员工薪资、全球福利、中国迁移/裁员与第三方社保制度材料；法定/第三方制度不证明微软实际缴纳基数或团队执行。20为保守网络扣账，不是完整账单；tokens估计预约不等于精确Deepseek tokenizer硬保障，美元成本未知。

第一次拟携带私人四维标准的研究升级被自动审批拒绝，命令未启动。随后公司模式改用纯公共事实采集清单；助手审计 initial System/Human payload 无个人薪资偏好、CV、JD、联系方式或本地路径，新的不同公共payload获准后运行。产物manifest冻结运行脚本hash；运行后company输入closed-schema的加强提交不追溯改变该run，固定评分使用原有同版四维rubric。

## 产物与复现

完整产物为 [company-reuse-2026-10-08](../../data/experiments/company-reuse-2026-10-08)，Git 忽略；本报告是版本管理中的结果。`bundle.json`、`baseline-cases.json`、`samples.json`、`sources-manifest.json`、`comparison-manifest.json` 冻结输入与本地出处；`check-v2/` 与 `baseline-check/` 为发送前检查，旧 check/initial snapshot 保留。`cold/`、`warm/`、`jd-probe/`、`baseline/`、`store/requests/` 保留请求、原始响应、cache/hash/history；`fixed-source-checks.json` 和 `offline-validation.json` 为助手核查。

`run-fixed.py` 使用 `jev-head-snapshot.py` 的已验证提交 transport，不覆盖工作区既存脚本；每个新 run 使用新目录，相同 request hash 成功缓存才可复用。复现缓存效果无需再次付费：

```bash
.venv/bin/python -B scripts/experiments/company-score.py \
  --input data/experiments/company-reuse-2026-10-08/bundle.json \
  --store data/experiments/company-reuse-2026-10-08/store \
  --output data/experiments/company-reuse-2026-10-08/NEW-WARM-RUN
```

Root 在 source registry 去重及 public-only 公司研究修正后重跑 company/adaptive 窄检查、233 文件 syntax 和 workflow-scan 均通过；实现提交为 `83094e03`、`01310edc`、`a68c3313`。Root 用实际 CLI 再次运行七岗：`root-warm-verification/` 显示九项全部缓存、零新增 API；独立复算公司研究的11份正文哈希和79片段位置一致。本轮固定源真实 API 行为及离线边界另见上述产物。

当前实验使用两个明确步骤：先按公司采集公开资料并整理带适用范围的档案，再由岗位引用公司档案和缓存评分。尚未把新公司发现、自动补查或定期刷新串入正式 score 工作流。正式接入仍待用户审阅，先决定实体/scope、更新/失效策略及推荐充分性验收。
