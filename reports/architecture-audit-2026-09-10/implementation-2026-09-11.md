# Hermes 场景精简实施记录

实施位置：`/Users/oii/.codex/worktrees/948e/career-ops`。仅修改 worktree，未提交，未修改生产 checkout、Hermes skill 或现有 cron。

## 已完成

- 删除 `web/`、`dashboard/`、`build-dashboard.mjs` 及仅服务这些界面的测试。
- 清理 npm 命令、Web 发布配置、Go CI/依赖更新、Docker Go 工具链、更新器 UI 路径和重建逻辑，以及当前文档中的 UI 入口。
- 删除仅供界面使用的状态分组字段和 follow-up 锁包装函数；保留底层锁、原子写入、状态校验与 CLI 数据契约测试。
- 原 Web 更新日志原样保存在 `docs/history/web-changelog.md`。
- 保留扫描、评估 A、人工选择后的申请准备 B、事实溯源和用户数据边界。未移动 cron 调用的 CLI 入口，未增加调度器。

Git 跟踪文件差异为 336 个文件、增加 105 行、删除 43,310 行；另保留 150 行历史更新日志，净减少约 **43,055 行文本**。该数字包含测试、文档、锁文件和资源，不等于业务代码行数，也不计审查附件。

## 验证

在 `/private/tmp/career-ui-validation-c6tv0hj5/` 创建原始 HEAD 和精简版本的独立 Git 快照，避免未暂存删除干扰按 Git 文件列表执行的检查。依赖使用生产 checkout 已安装依赖的副本，未修改其依赖。

| 检查 | 原始基线 | 精简版本 |
|---|---:|---:|
| 完整 Node 测试 | 5,252 通过 / 7 失败 / 2 警告 | 5,197 通过 / 7 失败 / 1 警告 |
| tracker 列契约定向测试 | — | 36 通过 / 0 失败 |
| JavaScript 语法检查 | — | 465 个文件通过 |
| 修改过的 YAML/JSON 解析 | — | 通过 |
| SYSTEM_PATHS 检查器自测 | — | 通过 |
| git diff --check | — | 通过 |

基线使用原有 `--quick` 跳过 Go 构建，精简版本已无 Go 构建分支，使用默认完整测试。删除界面专属测试后，通过项数量相应减少。两者失败项完全一致：

1. 更新器覆盖登记遗漏 5 个文件：`.codex/config.toml`、`lib/prescreen-cache.mjs`、`lib/prescreen-core.mjs`、`preparation-plan.mjs`、`prescreen.mjs`。
2. `modes/scan.md` 缺少外部不可信内容指令引用。
3. batch prompt 的 HTML 输出与渲染路径断言失败。
4. batch 最终 JSON 类型与转义序列化断言失败。
5. batch worker 独立计算 tracker 编号的断言失败。
6. batch Machine Summary 的 `reports_to` 字段断言失败。
7. live archive 测试中 Chromium 因运行环境权限无法启动。

本次未修复这些既有问题；完整测试仍未全绿。日志位于 `/private/tmp/career-ui-baseline.log` 和 `/private/tmp/career-ui-final.log`，属于临时验证产物。

## 保留范围

其他模型运行器、插件、市场语言包和 LaTeX 尚未删除：主要使用 Hermes 并不证明这些业务能力没有消费者。未迁移数据目录或改变 A/B 行为。后续从上游更新时，需要检查其是否恢复已删除的 UI 文件；本次没有另建更新框架。

## 基线失败修复（2026-09-11）

- 四个预筛选/准备业务文件加入更新器系统清单；`.codex/config.toml` 按仓库开发工具配置从分发覆盖检查中排除，文件本身保留，不作为 Hermes 运行依赖分发。
- scan 现有不可信内容规则链接至 AGENTS.md 的统一规范。
- 移除过时 HTML/PDF 路径断言；最终 JSON 按 Stage 1 的 `pdf: null` 检查，报告编号检查实际 runner 预留与注入路径；`reports_to` 检查按同级标题边界截取。
- 默认测试明确报告真实归档 NOT VERIFIED；`node test-all.mjs --live-archive` 显式启用，缺少浏览器、拿不到岗位 URL或渲染失败均导致失败。
- 已在获准启动 Chromium 的临时目录独立运行真实岗位归档：成功生成 237.4 KB PDF；提取 18,265 字符，含目标公司和岗位标题。未向生产数据目录写入。

修复后完整默认测试：**5,202 通过、0 失败、2 警告**；465 个 JavaScript 文件语法检查通过，`git diff --check` 通过。完整日志：`/private/tmp/career-baseline-fixed.log`。真实浏览器归档已按上文单独验证。
