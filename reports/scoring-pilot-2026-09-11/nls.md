# 试评：实际雇主未披露（NLS 招聘代理） — AI Engineer - Global AI Fintech Firm - Hong Kong

历史快照方法验证；不覆盖旧分数，不进入正式申请队列。

## Machine Summary

```yaml
scoring_model: attractiveness-v1
scope: pilot
score: null
company: 实际雇主未披露（NLS 招聘代理）
role: AI Engineer - Global AI Fintech Firm - Hong Kong
complete_jd: true
jd_source: nls
sources:
  - id: cv
    path: reports/scoring-pilot-2026-09-11/evidence/cv.md
    sha256: cb6d7f5da796f39b791722fcf9afff3bce8fec66dbc250b7a6b59787c2693ed5
  - id: profile
    path: reports/scoring-pilot-2026-09-11/evidence/profile.yml
    sha256: 78b3c64dcceb23ca27efe436059b87d722a38ca10ba6b8cfc5ac38301774d80c
  - id: targeting
    path: reports/scoring-pilot-2026-09-11/evidence/targeting.md
    sha256: af70f2b0e367d7c0793f74142f7c05e36359ddc99a5afd9e85c0aed8e6d6fbf4
  - id: nls
    path: reports/scoring-pilot-2026-09-11/evidence/nls.md
    sha256: ffd841adc7e3512f386470cf1b88d4c3b67c50488a8ce0baa4dbb0b2bc8b2aee
  - id: rules
    path: reports/scoring-pilot-2026-09-11/evidence/rules-round2.md
    sha256: 70a1a2bd51cdf321e0202fec448032d6e8193c03cf3f875e625243088e8902e2
dimensions:
  direction:
    score: 4
    rationale: 按第二轮锚点独立判断为 4：Python / Rust / TypeScript 应用开发、Agent 编码评审工作流以及产品 UX 贡献明确符合全栈和 AI 工程方向。但 JD 对 Agent 的主要描述是生成与评审代码的方法，没有明确说明首选 Agent / Applied AI 产品系统是交付主体；因此不满足 5 的产品主业条件。
    evidence:
      - source: nls
        quote: Define and iterate on agent “rules,” skills, and workflows for code generation and review.
      - source: nls
        quote: Help shape product and UX through feature design and practical engineering input.
      - source: targeting
        quote: '| Secondary | **Full Stack / Backend Engineer** | TypeScript and Python services, contract-first APIs, testing, data, deployment, and operations |'
      - source: nls
        quote: Create and maintain various applications using Python, Rust and Typescript.
  compensation:
    score: null
    rationale: 上限 HKD 1M 说明潜力，未证明保证底薪与实际可得区间，无法确认达到 HKD 720K 底线或 HKD 900K–1.1M 目标，故整个维度未知。
    evidence:
      - source: nls
        quote: Posted 4 days ago  Permanent  Up to HKD 1,000,000 per annum
      - source: targeting
        quote: 'Hong Kong five-day-role baseline: HKD 720K annual gross base salary (HKD 60K/month); target HKD 900K-1.1M annual gross base salary.'
  team:
    score: null
    rationale: 弹性时间和混合办公是工作安排上的正面线索，但远程频率、实际工时、五天制及管理实践未明，无法据此判定整个 team 维度；产品职责不重复加分。
    evidence:
      - source: nls
        quote: Flexible work schedule in a hybrid setup
      - source: nls
        quote: Influence engineering practices and team culture as the organization scales.
  company:
    score: null
    rationale: 匿名客户的 global / expanding 描述不足以核实业务前景、稳定性和技术投入；招聘代理 NLS 的人数不能代表实际雇主。
    evidence:
      - source: nls
        quote: Our client, a global AI fintech company, are actively seeking an experienced Senior Software Engineer to become a vital part of their expanding engineering team.
attractiveness:
  lower: 2.05
  upper: 4.65
  coverage: 0.35
```

## A. 岗位概览

历史 2026-09-07 JD 快照试评，未复核当前有效性。职责是 Python/Rust/TypeScript 应用、AI 辅助代码生成与审查、产品及 UX 参与。岗位主要是软件工程与编程 Agent 工作流，不因标题含 AI 就当作主要建设用户 Agent 系统。NLS 是代理，实际雇主匿名。

- [cv](evidence/cv.md) — SHA-256: `cb6d7f5da796f39b791722fcf9afff3bce8fec66dbc250b7a6b59787c2693ed5`
- [profile](evidence/profile.yml) — SHA-256: `78b3c64dcceb23ca27efe436059b87d722a38ca10ba6b8cfc5ac38301774d80c`
- [targeting](evidence/targeting.md) — SHA-256: `af70f2b0e367d7c0793f74142f7c05e36359ddc99a5afd9e85c0aed8e6d6fbf4`
- [nls](evidence/nls.md) — SHA-256: `ffd841adc7e3512f386470cf1b88d4c3b67c50488a8ce0baa4dbb0b2bc8b2aee`
- [rules_round2](evidence/rules-round2.md) — SHA-256: `70a1a2bd51cdf321e0202fec448032d6e8193c03cf3f875e625243088e8902e2`

## B. 能力竞争力

以下逐项基于冻结 [CV](evidence/cv.md) 与 [JD](evidence/nls.md)，技能列名仅证明被列出，深度需另核。Proven 只覆盖当前行的要求。

| JD 要求 | 判定 | 候选证据 | 招聘影响 | 应对 |
| --- | --- | --- | --- | --- |
| Python/Rust/TypeScript 应用开发，语言至少一项 | Proven | cv.md 有 Python/TypeScript 及生产 TypeScript 全栈交付 | 语言择一有证据，Rust 未证不构成单独硬缺口 | 以 TypeScript 生产案例回应 |
| 指定语言至少4年经验 | Unverified | cv.md 只明确三年以上专业交付，未给单语言四年证明 | 年限竞争力需核实，不能靠方向高分掩盖 | 按实际工作日期与语言使用范围确认 |
| 最好1年以上 AI/ML 生产经验 | Unverified | cv.md 2025-09至今含生产Agent；具体上线日期不明 | 是偏好项，约一年不是精确满一年 | 确认开始与上线日期 |
| 相关学历或等价经历 | Proven | cv.md Education 软件工程硕士 | 学历有直接来源 | 照实呈现 |
| 编写代码并逐步引导 Agent 生成代码 | Adjacent | cv.md Personal workflows：Claude Code/Codex/Cursor规则与hooks | 个人工作流不能直接扩成企业推广成果 | 演示真实工作流与人工校验 |
| 编程 Agent 规则与工作流配置 | Proven | cv.md 明确 Cursor Rules/hooks、Codex plugin 与个人自动化工作流 | 个人实践也是有效证据，JD不要求组织级平台 | 展示实际规则与工作流 |
| Agent skills 与代码审查工作流迭代 | Unverified | cv.md 未具体证明代码审查及skills迭代记录 | 不从工具使用推断完整审查能力 | 核实实际生成、审查和迭代环节 |
| 校验 Agent 输出并迭代 | Adjacent | cv.md 有生产业务 Agent 回归与编程工作流 | 业务输出评估可迁移，代码Agent评测另核实 | 讲评估方法并明确对象差异 |
| 可靠、安全系统设计 | Proven | cv.md VivoFlow 访问权限、敏感字段、测试与生产运维 | 直接工程证据 | 讲权限设计和故障恢复 |
| 对齐客户需求和产品路线 | Proven | cv.md Kupo World 用户研究到发布；VivoFlow 产品交付 | 产品判断有证据 | 给需求取舍实例，不编造客户行业 |
| 产品与 UX 设计 | Proven | cv.md Troph 产品设计与交互经历 | 直接相关 | 选择真实产品案例 |
| 影响工程实践和团队文化 | Adjacent | cv.md Huawei 领导三人团队；未证明规模化组织建设 | 小团队经历可迁移 | 明确三人范围及具体实践 |

## C. 入职吸引力

**入职吸引力：** 2.05–4.65/5；证据覆盖率：35%

| 维度 | 分项 | 权重 | 依据与限制 |
| --- | --- | --- | --- |
| direction | 4 | 35% | 按第二轮锚点独立判断为 4：Python / Rust / TypeScript 应用开发、Agent 编码评审工作流以及产品 UX 贡献明确符合全栈和 AI 工程方向。但 JD 对 Agent 的主要描述是生成与评审代码的方法，没有明确说明首选 Agent / Applied AI 产品系统是交付主体；因此不满足 5 的产品主业条件。 |
| compensation | Unknown | 30% | 上限 HKD 1M 说明潜力，未证明保证底薪与实际可得区间，无法确认达到 HKD 720K 底线或 HKD 900K–1.1M 目标，故整个维度未知。 |
| team | Unknown | 25% | 弹性时间和混合办公是工作安排上的正面线索，但远程频率、实际工时、五天制及管理实践未明，无法据此判定整个 team 维度；产品职责不重复加分。 |
| company | Unknown | 10% | 匿名客户的 global / expanding 描述不足以核实业务前景、稳定性和技术投入；招聘代理 NLS 的人数不能代表实际雇主。 |

未知维度范围均为1–5；没有额外风险加减分。此范围不是统计置信区间，中点不是预测。当前建议优先补证，不把区间上限当作可兑现待遇或最终满意度。

## D. 薪酬与需求

广告原文为 “Up to HKD 1,000,000 per annum”，另写 equity opportunities。上限不是保证底薪，也没有工资下限；因此 compensation=null。数字看起来接近个人 HKD 900K–1.1M 目标，只能成为优先询价线索。核实保证底薪、奖金/股权构成、职位带宽与实际职级；不能用股权补足 HKD 720K 底薪门槛。

## E. CV 变更计划

突出 TypeScript/Python 全栈交付、产品与 UX、编程 Agent 工作流和安全可靠性；保留个人工具实践与企业生产成果边界。业务 Agent 评估不改写为代码生成平台评测；省略未证实 Rust 与四年以上单语言经历。不因代理客户匿名而补造雇主成果或行业经验。本轮不生成 CV。

## F. 面试与补证

先问实际雇主、直签合同与员工规模，核底薪及香港工作安排支持。将 hybrid 作为正面补证线索，询问每周远程天数、总工时、经理协作方式与加班补偿；再确认四年语言经验的弹性以及岗位到底建设何种 AI 系统。

## G. 岗位真实性

仅能确认历史招聘板快照含岗位正文及代理信息。没有实时有效性核验或实际雇主验证，当前真实性 Unknown。NLS 页面12名员工是代理人数，不得用来判实际雇主不满50人，也不能据其“global”叙述判断规模。

## Risk Summary

| 风险 | 当前结论 |
| --- | --- |
| 有效性 | Unknown：历史快照，未实时核验 |
| 公司与雇佣 | Unknown：见Checklist；不计入能力竞争力 |
| 待遇与工时 | Unknown：不以招聘话术代替确认 |
| 能力差距 | 按B逐项展示；不重复扣吸引力 |
| 面试红旗 | 未评估：本次没有面试事实 |
| 重复计分 | 无额外风险扣分；工作职责归direction，实际管理/安排归team |

## Evaluation Checklist

| 公司门槛 | 状态 | 证据 | 下一步 |
| --- | --- | --- | --- |
| 地点 | Pass | 历史JD明确 Hong Kong，仅针对快照地点 | 实际办公地点和受雇支持仍需确认 |
| 雇佣 | Unknown | Permanent 标签不证明实际雇主直签 | 核实雇主与书面员工合同 |
| 规模 | Unknown | NLS的12人不等于匿名雇主规模 | 核实实际雇主至少50人 |
| 工时 | Unknown | flexible hybrid，无五天制与实际工时 | 核实远程频率、工时和值班补偿 |
| 待遇 | Unknown | Up to 1M，没有保证底薪范围 | 确认底薪及奖金股权构成 |
| 真实性 | Unknown | 历史招聘代理快照，未实时验证 | 核实原帖与实际招聘实体 |

能力问题逐项见 B；CV 选择与禁止扩张项见 E。公司未知项先补证，能力竞争力另核实。此历史试评不声明 Stage 0 已通过，不启动申请。
