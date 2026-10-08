# OII-397：完整正文与按缺口研究的隔离试验

本轮完成了五个保留岗位的隔离研究和同版本四维前后评分。取得了超过旧 4000 字截断的正文，也实际超过了旧工具次数；新增材料有价值，但**五岗研究均为 partial，不能据此宣称已查全或直接切换正式推荐**。正式评分、DB、cron、Dashboard 和充分性阈值均未改变。用户已接受近似小数锚点，本轮不把微小分档偏移作为阻塞。

使用当前配置的研究模型 `deepseek-v4.1-flash`、`xhigh`，复用 `career_ops.llm.invoke`、LangGraph 节点和 Tavily adapter。工程实现使用 6.1 Sol。当前标准为 [four-dimension.md](../../rules/evaluation/four-dimension.md)，冻结 SHA256 `89eab205cc1369791b117e4d0801cbba0e969761fe50b99e1573f24a7c254c5f`；五对输入的 `posting` 与旧研究保持相同，只增加本轮公开研究材料。前后都调用 Jev `jev-1.13.0`，不是将历史三维 company 当作文化金标。

## 产物与复现

原始数据位于 [`data/experiments/adaptive-evidence-2026-10-08`](../../data/experiments/adaptive-evidence-2026-10-08)。该目录不纳入 Git；本报告为版本管理中的结果摘要。

- 主研究：`62-v2-final/`、`9/`、`121/`、`162/`、`130/`。每岗保存 rubric、原始 baseline、实际 prompt、messages、完整 provider JSON、`bodies/*.txt`、ledger、handoff-evidence、paired-cases。
- `62/` 是首次预算估计失败的 pilot；`62-v2/` 是第二次采集的原始记录。`62-v2-final/` 仅复制已有来源并作一次无工具收尾，没有第三轮重新搜索。旧文件均保留。
- `score-run/*.request.json`、`*.attempt-*.raw.txt`、`*.json` 和 `results.json` 保存 Jev 原始请求/响应；`summary.json` 保存不取整的完整分数、confidence、Noul 和资源统计。
- `9/context-selection.json` 记录原请求 400 后删除的一段 image data URI 及原 offset/hash。`9/relevant-case.json` 是可被Jev接受的同来源上下文变体；不是新岗位或重新采集。
- `local-read-proof/verification.json` 是研究结束后的**本地工具回查验证**，不计新增外部研究，也没有送进评分请求。
- `jev-score.snapshot.py` 来自已验证的 `d1efed79`，避免覆盖工作区既存的 `jev-score.py` 修改。`replay.py` 使用已成功请求的原始缓存，新请求先移除本地路径；`handoff.py` 对早于最终 handoff 修正启动的 run 生成实际来源交接。原始外发请求/响应保持原样。

新隔离入口示例（必须使用新输出目录，拒绝覆写旧 run）：

```bash
.venv/bin/python -B scripts/experiments/adaptive-research.py \
  --cases data/experiments/jev-evidence-gaps-2026-10-08/corrected/cases.json \
  --seeds data/experiments/jev-evidence-gaps-2026-10-08/corrected/sources.json \
  --job 62 --output data/experiments/NEW-RUN/62
```

Jev 本轮复现依据是保存的 request 和适配器 snapshot；有缓存时 `replay.py` 不再次发已成功请求。它保留先前请求的 hash，不能把不同上下文伪装成相同请求。

## 资源与实测停止

每岗默认 900 秒进程硬截止，870 秒后不发新模型请求；Tavily 请求还要求预留其 60 秒 adapter timeout。网络预算保守按 search 1 credit、extract 每 URL 1 credit 请求前扣账（含失败），最多 20，防止多 URL 单调用绕过额度。相同 query 和成功/失败 URL 复用记录，不再次 dispatch；同一文章的不同转载 URL 仍可能重复，未声称语义去重已经解决。

模型资源为 150K tokens：以 `cl100k_base` 加 20% 余量预约输入、按剩余资源动态限制输出，再用 provider 返回实际 usage 替换成功预约；失败未知用量保守保留预约。它是请求前估计和请求后记账，**不是 Deepseek 精确 tokenizer 或绝对 token 硬上限证明**。没有配置价格表；模型、Tavily 和 Jev 的美元费用未知，不把 tokens/credits 换成伪美元成本。

| 岗位/run | 时间秒 | search / extract / 本地回读 | provider bodies（>4000） | 最大正文字符 | 实际模型 tokens | 保守 credits / provider 返回 credits | 停止 |
| --- | ---: | --- | --- | ---: | ---: | --- | --- |
| Bosch 62-v2-final | 约634¹ | 5 / 3 / 3 | 8（6） | 27,672 | 122,884 | 17 / 7 | token 预约不够后，一次无工具收尾撞输出上限；partial |
| Microsoft 9 | 289 | 5 / 4 / 2 | 7（6） | 34,643 | 125,416 | 13 / 7 | 下一次 token 预约不可支付；partial |
| NVIDIA 121 | 258 | 8 / 3 / 3 | 5（5） | 374,810 | 95,274 | 13 / 8 | 下一次 token 预约不可支付；partial |
| Inspire 162 | 232 | 10 / 1 / 3 | 8（7） | 27,064 | 114,738 | 18 / 11 | 下一次 token 预约不可支付；partial |
| Jane Street 130 | 61 | 3 / 2 / 0 | 7（5） | 14,026 | 47,341 | 10 / 5 | 模型自然结束，夹叙述的输出不是有效最终 JSON；partial |

¹ Bosch 时间为包含调试等待的约计墙钟观察值，采集本身约 236 秒；不是精确模型计费时长。收尾异常报回 input 40,378 / output 12,472（reasoning 7,276）/ total 52,850，与采集 70,034 合计 122,884。此收尾异常的 completion 正文未在单次临时 wrapper 保存，只保留异常类型与报回 usage；已修正主入口保存此类 parsed error completion 和已知 usage，不再追加收尾。

主五岗合计 20 次模型调用、505,653 个报回 tokens、31 search、13 extract、11 本地回读；保守网络扣账 71、provider 返回 usage 合计 38。首次 Bosch pilot 另有 117.6 秒、30,313 tokens、4 search/2 extract、9 bodies、保守13/返回6 credits，不混进主对比。provider 返回 usage 不等于完整账单，extract 的零值不能理解成免费；Jev 响应未提供可用于定价的 token/费用数据。

35 份 body 合计 853,597 字符，其中29份超过4000；它们是 **provider 返回文本的完整冻结**，不是整个网站 HTML/PDF 完整性证明，也不是35个独立网站或有效事实的数量。包括 Wikipedia 长文、导航、广告、重复转载和 SVG/base64 噪声。Tavily 明确失败 URL：Bosch4个、Microsoft1个；另外存在 HTTP成功但仅返回导航/空金额表的内容失败。不同转载反复谈同一收购，并不构成多个独立证据。

NVIDIA 的 8 search 和 Inspire 的10 search 实际超过旧5次，四岗 extract 超过旧1次；没有将 Inspire 仅1次 extract、MS恰好5次search说成所有岗都超过限制。实际197个已读范围的 body hash 和 `text == body[start:end]` 经助手独立回查通过；这是可追溯性检查，**不是用户金标或 claim 语义验收**。本地额外回查 Microsoft 年报 `[16970,17350)` 成功取到 4000 字之后的研发表数字32,488；模型当时未读该段，所以它不在已评分的上下文中。

## 同 rubric、同保留 JD 的前后结果

每个格为 **原始分数 / 原始 confidence / 独立 Noul 充分性**。下表只将显示值取两位；原始小数和分布在 results/response 中完整保留。没有取整、封顶、平均、总排名或设置充分性阈值。

| 岗位 | 维度 | baseline | adaptive |
| --- | --- | --- | --- |
| Microsoft 9 | direction | 4.97 / 0.99 / 0.86 | 4.97 / 0.98 / 0.88 |
| Microsoft 9 | company | 3.54 / 0.51 / 0.07 | 3.29 / 0.53 / 0.22 |
| Microsoft 9 | culture | 3.07 / 0.42 / 0.09 | 3.04 / 0.40 / 0.10 |
| Microsoft 9 | compensation | 2.15 / 0.03 / 0.03 | 1.99 / 0.18 / 0.04 |
| NVIDIA 121 | direction | 3.99 / 0.99 / 0.84 | 3.99 / 0.99 / 0.82 |
| NVIDIA 121 | company | 3.69 / 0.54 / 0.11 | 4.14 / 0.48 / 0.23 |
| NVIDIA 121 | culture | 2.64 / 0.42 / 0.08 | 1.89 / 0.64 / 0.13 |
| NVIDIA 121 | compensation | 4.30 / 0.54 / 0.11 | 4.15 / 0.70 / 0.20 |
| [Bosch 62](https://jobs.smartrecruiters.com/BoschGroup/744000096326604-nlp-llm-ai-agent-cr) | direction | 4.21 / 0.34 / 0.82 | 4.25 / 0.37 / 0.81 |
| [Bosch 62](https://jobs.smartrecruiters.com/BoschGroup/744000096326604-nlp-llm-ai-agent-cr) | company | 3.14 / 0.83 / 0.14 | 3.26 / 0.68 / 0.35 |
| [Bosch 62](https://jobs.smartrecruiters.com/BoschGroup/744000096326604-nlp-llm-ai-agent-cr) | culture | 3.33 / 0.39 / 0.09 | 4.18 / 0.65 / 0.21 |
| [Bosch 62](https://jobs.smartrecruiters.com/BoschGroup/744000096326604-nlp-llm-ai-agent-cr) | compensation | 1.79 / 0.31 / 0.03 | 1.80 / 0.34 / 0.04 |
| Inspire 162 | direction | 4.98 / 0.99 / 0.76 | 4.96 / 0.97 / 0.74 |
| Inspire 162 | company | 3.21 / 0.79 / 0.08 | 3.69 / 0.63 / 0.17 |
| Inspire 162 | culture | 3.57 / 0.51 / 0.13 | 3.54 / 0.53 / 0.14 |
| Inspire 162 | compensation | 2.64 / 0.00 / 0.06 | 2.47 / 0.00 / 0.05 |
| [Jane Street 130](https://www.janestreet.com/join-jane-street/position/8637960002/) | direction | 3.39 / 0.65 / 0.25 | 3.37 / 0.68 / 0.27 |
| [Jane Street 130](https://www.janestreet.com/join-jane-street/position/8637960002/) | company | 3.22 / 0.64 / 0.06 | 3.43 / 0.55 / 0.16 |
| [Jane Street 130](https://www.janestreet.com/join-jane-street/position/8637960002/) | culture | 2.88 / 0.33 / 0.08 | 2.76 / 0.32 / 0.13 |
| [Jane Street 130](https://www.janestreet.com/join-jane-street/position/8637960002/) | compensation | 3.92 / 0.12 / 0.12 | 4.31 / 0.43 / 0.18 |

最终五对10请求均有效，另保留 Microsoft 原 `9-adaptive` 请求的 HTTP400 `max_tokens_exceeded`：原请求约75,218字符；没有重发同一失败请求。新 `9-adaptive-relevant` 仅删除已实际读取范围内一段 SVG data-URI 图像段，保留其他文本的原 offset/hash，约47,605字符的 case，成功评分。正文原样保存。检索放开不代表 Jev 上下文无限。

company 充分性五岗都有提升；评分本身并非一律上升，Microsoft 在取得中国 Azure 裁员材料后由3.54降到3.29。culture 充分性仍为.10–.21；compensation 为.04–.20，Inspire还由.06降至.05。Bosch culture4.18不证明已确认正常双休和净40小时，NVIDIA company4.14也不证明本地岗位安全；仅凭原始分>=4或高confidence不能补足独立证据缺口。当前没有把这些岗位转成确定 focus/推荐。

## 助手独立证据审阅

| 岗位 | company 新支持与限制 | culture 新支持与缺口 | compensation 新支持与缺口 |
| --- | --- | --- | --- |
| Microsoft 9 | 取得官方FY2025经营正文，以及中国Azure裁员新闻；FY2025不是FY2026，Azure范围不能自动归于UIPilot。完整年报中有研发表，但本轮模型没有回读该相关段。 | GCR官方页和全球福利页可证明部分制度描述及按地区变化；全球页明示细项目前美国适用，Levels福利含401K/Bay Area，不能填中国社保、公积金、年假或团队作息。净工时仍未知。 | 中国SDE II Levels页面仅空表和图像，没取得可用薪资金额。不能据URL、旁站金额或制度说明填报价/底线。新材料并未修复金额缺口。 |
| NVIDIA 121 | 官方FY2026全年及较早季度经营正文、实际产品工程及中国H20风险；集团经营有用，不保证北京软件岗位安全。Wikipedia为二手线索，不能替代原始技术/风险出处。 | 新闻转载包含中国员工加班、半夜待命及离职体验，能提示实质风险，但部门、周期、独立性有限；不能算出本岗位固定净工时。当地假期、社保公积金基数比例未补齐。 | 北京Levels IC2/3/4分别531K/621K/948K CNY总薪酬及base/stock/bonus有适用基准价值；本岗未定级、自报不等offer。ESPP/RSU报道是制度线索，文中称RSU“期权”不作为精确法律形式；不能保证授予或兑现。 |
| Bosch 62 | 官方H1经营、利润/现金流/人员收缩与软件订单等支持两方面调查；集团和欧洲收缩不直接证明上海团队；同事件转载不重复计独立证据。 | 中国官方弹性安排/绩效奖金；牛客多条自述含作息、15天年假，另WonderCV为创新软件中心转载，含12%全额公积金、13薪、年假病假。不同部门、年限及执行独立性未核实，不能套到本CR岗位；仍未知自由午休、待命和净工时。 | 奖金制度有依据，金额未取得。中心转载的13薪和12%不能变成本岗保证offer/基数。文化原分上升不替代这些范围检查。 |
| Inspire 162 | Thoughtworks官方收购协议与多次相同转载、企业索引、Inspire内推说明有实体/交易线索；计划注资及“预计完成”不等已完成交易与已发生投入，收购后持续经营/技术建设仍弱。 | 部分内推只取到导航，没取得本地带薪假、公积金基数比例、实际加班执行。检索末尾出现“英伟”等错实体查询，未形成可用证据；跨城/旧Thoughtworks惯例不填成都当前制度。 | 没有取得可比金额、绩效基准或适用股权兑现条件。不能把融资、公司改名或校招制度当本岗位年薪。 |
| Jane Street 130 | HK官方工程岗位提及实际OCaml/开源建设；经营数字主要来自二手报道和Wikipedia，不是完整官方财报，不能把全部全球收入当香港工程安全。 | 工时文章依赖2021年离职员工、地区未明确且没有自由午休/待命；9–18不等净40，也没有六天工作周依据。官方福利多地区混排；模型选到8个重复“90%进修报销”段，未充分回查相关章节。模型总结中的“6天/双休”、20天假等没有本轮可靠适用支持，不能作为事实。 | HK Levels L1总2.04M/base2.01M/bonus25.1K HKD是相关地区基准，但本岗职级未知、基准不是保证base的offer；平均全球总薪酬/小时收入不能替代香港保证base。 |

五岗 direction 仍主要来自相同保留JD：MS/Inspire的Agent应用主责明确；NVIDIA属于相邻AI软件方向；Bosch同时包含应用Agent交付及post-training；Jane Street为通用工程/OCaml交易系统。小数轻微变化不证明研究改变了实际职责。

来源级问题不能靠原始分数掩盖：目前有可用事实，也有适用范围不足、相同转载、选段命中重复泛词而漏掉关键章节、JS金额空表、访问失败和模型格式/总结错误。预算是实测停止原因，未证明模型在“足证/重复无价值”时已经可靠自行停止。自动缓存仅避免相同请求，不保证识别跨URL重复或错地区。本文审阅是助手对冻结来源的核查，不是用户充分性金标；不要求每项福利齐全才充分，也不把官方承诺当员工执行。

## 外发边界与验证

外部研究及Typesafe目的地/payload已获用户授权。未发送CV、候选经历或联系方式。首批8个评分请求中4个补证请求意外附带 `full_body_local_path`/`body_file` 本地路径元数据，含 workspace 用户目录；这是多余元数据外发，不能泛称所有请求仅含公开材料。11份唯一原始请求中4份含此字段；后续 Microsoft新variant、Inspire请求已删除，本地manifest仍保留回查路径。原始外发请求没有事后改写，已修正入口的评分交接不再带这些字段。

Jane Street 先启动版本在自然结束时误标completed，实际最终输出夹叙述、格式无效；保存的初次Jev请求含该状态字段。当前handoff改为partial，旧请求和响应未改写，表中仍为当时原始输出。后续入口以有效最终JSON决定completed；摘要失败仍交接实际读过的来源，不依赖自动facts或用LLM生成替代分数。

验证通过：隔离窄check（全文保留、4000字后选段/回读、真实请求计数放开、预算前置、多URL扣账、重复/失败缓存、错结构拒绝、partial材料交接），`node scripts/check-syntax.mjs`（233文件），`.venv/bin/python -B tests/business/workflow-scan-test.py`，以及助手独立35份body hash/197段offset回查。正式流程未切换，本轮不继续调模型、扩大样本或追加研究。
