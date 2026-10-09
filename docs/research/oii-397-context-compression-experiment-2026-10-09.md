# OII-397：研究历史 compaction 与摘要前 Jev 筛选的真实实验

日期：2026-10-09。仅使用已留存的 Microsoft 公开公司资料；没有新搜索，没有发送 CV、个人薪资目标或私人评分标准，没有写业务数据库或修改正式算法。

## 结果

- **C：Jev 筛选完成，17/17 段全部保留。** 按来源重组后，传给摘要的输入与原始 read sections 相同；复用既有成功摘要，没有压缩收益。不能通过换一份随机生成摘要来证明筛选更有效。
- **B：三维单检查点真实对照均完成。** 后续规划输入减少约 78%–90%；但第一次“compaction＋继续”总 tokens，公司 +18.5%、文化 −1.2%、薪酬 +17.4%。文化此次调用等待缩短，其余两维首次等待增加。这不是实际美元成本比较，缓存与输出/推理用量也不相同。

当前样本支持“活动上下文会变短”，不支持“总体成本一定降低”或“事实组织质量稳定提升”。正式流程继续使用现有方案。

## 边界与材料

入口：[context-compression.py](/Users/oii/dev/career-ops/scripts/experiments/context-compression.py)。输出：[实验目录](/Users/oii/dev/career-ops/data/experiments/context-compression-2026-10-09)。生成模型为项目配置的 `deepseek-v4.1-flash`，Jev 为 `jev-1.13.0`。所有 compaction、规划、额外摘要及模型质量评审均由实际模型调用产生；人工审阅只解释结果，未改写生成 JSON。

冻结材料位于 `data/company-profiles/85ad9b65cb9417b067689d2e/evidence/`：

| 维度 | 原研究 | 既有成功摘要 | 适用范围 |
| --- | --- | --- | --- |
| company | capture-company-1 | summary-company-3 | global |
| culture | capture-culture-1 | summary-culture-2 | China |
| compensation | capture-compensation-2 | summary-compensation-2 | China:Beijing\|Shanghai\|Suzhou，Software Engineer 2，CNY annual_total |

B 与 C 每维各有独立 200K token 预算，没有共享总预算。失败恢复使用单独有界尝试目录；已有失败、用量和未知用量的保守预约保留。质量 judge 是测量费用，不计入方案运行收益。估算 tokenizer 为 `cl100k_base`，预约加 20% margin；reported usage 与估算预约分开。

## B：单检查点研究规划回放

选原始历史中约 60% 处、工具结果已经完整返回而下一条 assistant 尚未发生的边界。原历史作为不可信数据发送给现有生成模型，生成包含 facts、sources、conflicts、gaps、attempted_sources、next_steps 的 working state；再用相同规划提示分别继续原历史和压缩状态。没有新工具执行或网络搜索，因此这是**单检查点、plan-only 对照**，不是端到端自主研究或滚动多次 compaction 验收。

| 维度 | compaction total | 原历史 plan input / total | 压缩后 plan input / total | 压缩＋继续 total | 模型质量评审 |
| --- | ---: | ---: | ---: | ---: | --- |
| company | 26,988 | 21,209 / 31,043 | 4,728 / 9,806 | 36,794 | 完成，51,349 tokens 测量费用 |
| culture | 24,639 | 22,023 / 29,586 | 2,132 / 4,584 | 29,223 | 完成，33,329 tokens 测量费用 |
| compensation | 22,559 | 17,434 / 26,332 | 3,151 / 8,360 | 30,919 | 完成，33,875 tokens 测量费用 |

薪酬 compaction input 中报告 16,384 cache-read tokens；未压缩规划报告 cache-read=0。供应商本账户的当前收费口径/单价未核实，不能由 total-token 比例推断美元比例。未来多个规划轮次可能摊薄 compaction 费用，但本次只真实继续一次，未测持续迭代与重复压缩漂移。

| 维度 | compaction 秒 | 原历史继续秒 | 压缩后继续秒 | 压缩＋继续秒 | 首次 total-token 变化 | 首次调用等待变化 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| company | 64.27 | 97.47 | 50.48 | 114.75 | +18.5% | +17.7% |
| culture | 35.07 | 86.36 | 29.63 | 64.70 | −1.2% | −25.1% |
| compensation | 53.89 | 88.11 | 52.96 | 106.85 | +17.4% | +21.3% |

等待时间来自实际调用事件，排除 quality、首轮失败和限流等待；这些额外费用另列。薪酬来自最初并行阶段，公司的有效恢复为串行，负载条件并不完全相同；不能据此推断生产端到端速度。

### 公司质量的独立审阅

judge 找到两边各自的时间/来源问题，不构成“压缩一定提高质量”的结论：原历史 plan 把 2025 年的游戏取消/工作室关闭放进 2026 年重组；压缩后 plan 在这些项目上较保守，但 working state 错把 2025-07-02 称为 FY2026 首日，后续 plan 继承该错误，实际是第二日。压缩后 plan 还把未实际读正文的 GeekWire R&D/headcount 标题放入 supported facts，虽然保留了限制说明，标题仍只能作为线索。

working state 的 ~$80B AI 投入 claim 使用“invested”，同条 limitations 又说明是 company-stated plan 且未核实 capex；这一内部口径冲突须在下游保留与复查，不能由 judge 的笼统 supported 标签当作“已完成且持续投资”的证据。当前样本显示 baseline 本身也会出错，因此摘要/规划逐字一致或评分一致都不是正确性标准。

### 文化质量的独立审阅

judge 给出 no critical losses，人工回看仍有以下解释边界：

- working state 和压缩后 plan 都保留“20周产假＋6周陪产＋6周领养＋4周家庭看护，合计36周”。[官方2017冻结正文](/Users/oii/dev/career-ops/data/company-profiles/85ad9b65cb9417b067689d2e/evidence/capture-culture-1/bodies/9c73a2d87092e2ea.txt:8) 自己就使用“共36周”宣传总数，因此这不是压缩凭空增加的数字；但正文同时区分女性产假、男性陪产、领养者和严重健康状况家属看护的资格，不能理解为单一员工可把四项一概叠加为36周。judge 的 supported 标签没有验证这种资格解释。
- 生成结果一边说20周约140天，一边暗示它可能高于同输出中的158天；这不是有效比较。2017企业政策与后来的地区法律综述也不在同一时间/资格口径，当前假期执行未核实，不能据这种对照判断实际待遇优劣。
- working state 保留了全球 Microsoft 365/Teams信号和中国法律综述，并标出非中国公司执行范围；压缩后 plan 没有把 Teams 信号当作微软中国员工工时，但仍列了部分法定规则作为 supported facts。法律背景、全球产品用户信号和微软中国实际执行必须分开，法定缴费率缺失不是微软执行事实被删除。
- 社保/公积金实际缴费基数、加班执行、当前福利天数仍是 gaps。这些 unknown 保留有价值；不能由来源综述替代公司事实，也不能因模型评审“faithful”就认定当前劳动法规已经独立核实。本次没有为纠正法律背景重搜或新增调用。

### 薪酬质量的独立审阅

LLM judge 认为城市口径、职级映射冲突和 unknown 大体保留，但其 verdict 不是人工金标。人工回看 working state 与 plan 后，需修正评审结论的解读：

- working state 保留了美国 Level 61/62 sign-on 上限，不代表保留了中国页面 FAQ 的 sign-on 事实。原来源 [92808f66be769c7d.txt](/Users/oii/dev/career-ops/data/company-profiles/85ad9b65cb9417b067689d2e/evidence/capture-compensation-2/bodies/92808f66be769c7d.txt:234) 写了“一次性、与 recurring annual bonus 分开”及 CN¥61,005 median；原历史 plan 提及，working state 与压缩后 plan 没有保留这条中国来源的完整条件。该来源自己把 one-time 与 per-year 放在一起，不能据此当成保证年薪或 SDE II 专属 offer。
- plan 被限制最多八条 facts；某条未出现在 plan 本身不能单独证明 compaction 删除。此次上述条件在 working state 也未保留，才构成需要进一步检查的召回问题。更不能用关键词 `sign-on` 命中证明地区/金额/条件仍然一致。
- Robert Half 行业薪资、旧 campus offer 均不属于当前 Microsoft 目标范围的有效薪酬事实。judge 把这些遗漏列入 critical losses 的部分不采纳；排除它们可以是正确行为。
- working state 把来源 2026-09-29 日期称为 future/anomalous；薪酬首轮请求没有明确 as-of 日期，存在实验 harness 混淆因素，不能称为 compaction 必然失败。公司/文化恢复对照两边均明确 `evaluation_as_of=2026-10-09`；原薪酬结果照实保留，没有为此收费重跑。

## C：实际 Jev 筛选，未获得压缩

将各维已读取 sections＋source header 按段落分块，过长段落必要时分片。每段问两项 Noul：是否提供当前维度/范围相关证据；是否含限制、条件、反证或避免过度解读所需上下文。**仅在两项都低于 0.2 时删除**，其余保留，原文由代码复制。0.2 是本次实验筛选参数，不是正式证据充分性或推荐阈值。

实际调用及按返回概率重算的保留率：

| 维度 | Jev 请求数 / Noul 数 | 0.2 保留 | 0.5 保留 | 0.7 保留 | 0.9 保留 | Jev input tokens | 输入价估算 USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| company | 2 / 16 | 8/8 | 8/8 | 8/8 | 4/8 | 19,040 | 0.00079968 |
| culture | 2 / 10 | 5/5 | 5/5 | 4/5 | 2/5 | 13,767 | 0.00057821 |
| compensation | 1 / 8 | 4/4 | 4/4 | 4/4 | 3/4 | 8,997 | 0.00037787 |

共 5 请求、34 个 Noul，输入 41,804 tokens，输出 666 tokens；按官方输入 $0.042/M、输出免费估算合计 **$0.00175577**，不是账单 readback。三维 Jev 请求累计等待约 1.45 / 1.35 / 0.70 秒；这些是分维请求时间和，不是整体研究/摘要耗时。[TypeSafe Models](https://docs.typesafe.ai/models)

0.5 仍全保留；更高阈值的表只揭示敏感性，不证明删掉的段落可以安全丢弃，没有为了得到压缩比例强行调阈值。此材料已经经过现有 `read_sections` 定向选取，不能把结果外推到未筛选的整站全文。

首轮实验错误地每段重复 source_header 等元数据，company 序列化输入估算从 13,247 增到 14,749，culture 从 11,976 增到 12,596；compensation 块数与来源数相同。该首轮生成摘要不能作为“Jev 节省摘要成本”的证据。已改为按来源重组、header 只保留一次；[c-grouped-replay](/Users/oii/dev/career-ops/data/experiments/context-compression-2026-10-09/c-grouped-replay) 复用实际 Jev 响应，三维确认 filtered input 与原 sources 相同，直接复用历史成功摘要，没有新模型调用。

## 失败与额外实验费用

- 首轮 B 使用 8192 输出上限，三维均发生 reasoning/JSON 输出截断：reported total company 29,404、culture 30,218、compensation 25,760。失败不是 compaction 质量结论。之后沿用现有 32,768 上限，靠提示约束简洁。
- company/culture 第一轮大上限恢复遇到 RateLimitError，未知真实 usage 的两次预约分别合计 119,740 / 137,470；第三次预约触及本次 200K 预算，停止。本轮最初 harness 未完整保存该错误 body/Retry-After，不能把保守预约称为 billed usage 或当成零消费。此缺口在报告中保留；后续恢复保存原错误 metadata，并改串行。
- 初版两个进程同时写维度 usage.json，出现覆盖风险。最终 reported totals 从不可变模型 response/failure、Jev response 和 summary calls 重建，未知预约从失败摘要与实际返回用量反推；混合 usage.json 不作为唯一账本。恢复入口默认串行，output 目录加进程锁，不重置原尝试费用。
- C 首轮多余摘要实际使用 company 65,995、culture 27,950、compensation 16,576，共 110,521 reported tokens；三维额外 judge 也在 8192 截断，reported tokens 28,214 / 21,940 / 18,928，共 69,082。全部保留为额外实验/测量费用，未为这些 judge 再付费重试，也未把随机摘要差异写成筛选收益。

核对后的 [usage-reconciled.json](/Users/oii/dev/career-ops/data/experiments/context-compression-2026-10-09/usage-reconciled.json) 共 **609,905 reported tokens**：LLM 567,435、Jev 42,470。它包含失败、恢复尝试、两边规划、额外摘要和质量评审，不能作为某一方案单次运行成本。分解如下：

| 项目 | reported tokens |
| --- | ---: |
| B 有效 compaction＋两边 plan（三维） | 183,897 |
| B 成功 quality（三维，测量费用） | 118,553 |
| B 首轮8192截断（三维） | 85,382 |
| C 实际Jev筛选 | 42,470 |
| C 首轮多余摘要 | 110,521 |
| C 截断quality（测量费用） | 69,082 |
| 总计 | 609,905 |

另有 **257,210 未报告实际usage的失败预约**，单列保守计账，不加入 reported 总数、不推断实际收费为0。公司与文化串行恢复尝试分别报告 119,186 / 92,138 tokens，均未重置或隐藏此前费用。Jev 输入价已于2026-10-09重新核对；LLM完整美元成本仍未知，缓存 tokens 不换算美元。

## 判断与验证

C 不应接入正式流程：当前真实材料已经定向读取，额外 Jev 筛选只增加调用与成本。B 可减小活动上下文，但本次两维首次总用量上升，一维只有小幅下降且存在资格/数字比较问题。若后续研究确因长历史反复发送而受阻，再针对多轮真实继续验证摊薄效果、working-state 召回与恢复读取；这次结果尚不足以替换正式研究循环。

离线 `--check` 验证分段拼接原文、指定基线真实存在且成功；`node scripts/check-syntax.mjs` 和 `.venv/bin/python -B tests/business/workflow-scan-test.py` 已通过。运行原请求、原响应、usage、failure 均留在实验目录。正式评分与推荐策略由本轮其他切片处理，本入口未触碰；实验结束后本轮根任务已恢复评分调度，并核对评分与scan调度均为active。
