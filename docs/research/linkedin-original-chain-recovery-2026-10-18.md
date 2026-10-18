# 原 LinkedIn discovery 链路修复验收

2026-10-18。停止 Jev Ultrafast 方向，直接验证现有 Playwright provider。已修复公开详情页面缺少 JSON-LD 时被丢弃的问题；两个地区的最小采集均成功。没有接入登录浏览器，没有写入业务库或启动全量 discovery。

## 根因与修改

修复前运行原 `newExtractionPage` → `readPage` → `jobFromPage`：

- 香港 AI 搜索 HTTP200，读取成功，3.481 秒。
- CASETiFY 职位 `4468584583` HTTP200，能看到正文，但 `postings=[]`，报 `No unambiguous JobPosting on detail page`，3.240 秒。

这与历史 HTTP429 是两个独立问题。本次搜索可访问，并不证明历史限流已经消失。

原提取器只读取 JSON-LD，另有 eFinancialCareers 的站点专用提取。新增同样范围的 LinkedIn 公开 DOM 提取：仅限 LinkedIn `/jobs/view/`，canonical 的 LinkedIn 职位 ID 必须匹配当前页面，同时要求 h1、明确雇主和至少 200 字符的正文。原有 JSON-LD 优先；不放宽 provider 的有效详情校验。

正文从页面已经包含的完整 publisher markup 提取，保留段落。即使页面用 CSS 折叠，仍可读取末尾，不需要点击 Show more、登录或调用模型。登录墙、身份不匹配和缺少雇主/标题均不能通过。

## 实测结果

相同单页探针修复后：搜索 3.396 秒；CASETiFY 详情 3.245 秒，通过校验，返回标准化 JD 3,258 字符，包括最后一项 Cloud/operations 要求。

随后调用真正的 `search` provider，而非替换回调：两地区顺序执行，各用 `Full Stack`、最多 1 个有效职位、最多 1 页、35 秒采集窗口，沿用生产导航、限速、身份校验和标准职位转换。

| 来源 | 耗时 | 有效记录 | 职位 / 雇主 | JD 字符 |
| --- | ---: | ---: | --- | ---: |
| China | 11.448 秒 | 1 | Senior Fullstack Engineer - China / Whatnot，4365909223 | 3,609 |
| Hong Kong SAR | 11.051 秒 | 1 | Full Stack Developer (AI &amp; Innovation) / Taikang Asset Management (Hong Kong) Co. Ltd.，4470132798 | 1,678 |

两来源总墙钟 22.500 秒。模型请求为 0。来源因设为 `max_results=1` 而触及结果上限；不代表全量覆盖。未将网页文字视为岗位当前仍接受申请的证明。

## 回归与证据

- 新增浏览器 fixture 先复现相同 JobPosting 缺失错误，修复后通过：正文末行保留、页面无点击变更、canonical 错配拒绝、authwall 拒绝、缺少雇主/标题拒绝。
- 原 provider 测试、提取器测试、hydration 浏览器测试通过。
- `node scripts/check-syntax.mjs` 与 `.venv/bin/python -B tests/business/workflow-scan-test.py` 通过。
- 原始记录位于 `data/cache/experiments/linkedin-original-20261018/`：`before.json` 从修复前工具输出保留指标；`after.json`、`detail.json`、`listing.json` 为修复后记录；`provider.json` 为两个来源的实际返回；`probe.mjs` 为单页复现脚本。

剩余限制：本轮未出现 429，未测试持续采集负载，也未证明所有详情页均公开可读。现有 429 停止与登录墙失败处理继续保留；本修复解决内容提取，不保证 LinkedIn 访问稳定性。完整批次成功率应在后续正常运行中观察，不能用这两个成功样本外推。
