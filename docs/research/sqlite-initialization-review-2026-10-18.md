# 数据库初始化竞争：ponytail 审查与验收

What this change does: 打开业务库时只确保活动任务唯一索引存在，不再删除并重建它。多个本机 CLI 可以同时打开当前版本业务库，唯一约束持续有效。

## Must fix（已修复）

1. **初始化撤销约束并相互竞争**（`career_ops/db.py:148`）
   - **What this is:** `BusinessStore.__init__` 是 task、CLI、通知和申请通信共用的数据库入口。预计负载是单用户本机多个工作流和定时队列并存。
   - **Problem:** 每次打开都以自动提交方式先 DROP 再 CREATE 唯一索引。A、B 均执行 DROP 后，A 创建成功，B 报同名索引已存在；删除与重建之间也没有数据库唯一约束。8 个并发连接反复初始化的回归在修改前复现了正式运行中的同一个错误。
   - **Fix:** 直接使用 `CREATE UNIQUE INDEX IF NOT EXISTS`。当前定义仍是 `tasks(opportunity_id) WHERE status='running'`，不改变业务规则、数据或 API；删除一行，没有增加锁、重试、配置、依赖或迁移框架。
   - **If we skip it:** 多个正常工作流仍可能在打开数据库时失败，且临时失去任务唯一性保护。

## 验证

- 新增 `tests/business/workflow-store-concurrency-test.py`：8 个独立连接各打开 10 次，重复获取同一职位任务仍返回同一个 task；初始化不改变 schema_version；直接插入第二个运行任务被唯一约束拒绝；完整性与外键检查通过。修改前出现 `sqlite3.OperationalError: index one_active_task_per_opportunity already exists`，修改后通过。
- 另在临时数据库运行 8 个真实 Python 进程，各打开 10 次，全部成功，原任务保留。没有用生产业务数据做并发写入实验。
- `tests/business/workflow-recovery-test.py`、`tests/business/workflow-scan-test.py` 和 `node scripts/check-syntax.mjs` 均通过。
- 生产数据库只读检查：quick_check 为 ok，外键违规 0，没有同一职位存在多个 running 任务的记录。
- 审查了全部 BusinessStore 调用方、任务 start 的事务边界、现有 apply 迁移测试及相邻 DiscoveryStore 初始化；本次修复在共享入口完成，无调用方补丁。

## 临时文件清理

确认临时脚本均无活动进程后，清除本轮相关 189 个文件（645,818 字节）：`/private/tmp` 的 8 个 LinkedIn 探针、分发与验收脚本，以及正式运行目录中的临时脚本副本、初筛输入副本、队列/当前进度/交接快照、重复 CLI 输出和旧清单。没有增加常驻实验入口。

`data/cache/linkedin-production-20261018/` 仅保留 9 份验收材料：`before.json`、`discovery-run.json`、`discovery-timing.json`、`discovery.stdout.json`、`provider-input.json`、`source-sha256.json`、`new-opportunities.json`、`final-verification.json`、`prescreen-finished.json`。清理前后这些文件哈希一致。

原始来源捕获 `data/cache/configured-discovery/3f7713ee238949778c654c61208351f9/`、业务库 JD/任务/检查点、正式评分报告及历史研究报告均保留。此前正式运行报告中指向中间 `prescreen/`、`prescreen-serial/` 的路径已按本次清理要求删除；以最终验收材料及业务库为准。未改动无关的用户未跟踪文件。

Verdict: Ship. 复现错误已消除，唯一约束保持有效。

Lean: 生产代码减少 1 行；仅保留一份并发回归，没有额外恢复机制。

Not checked: 历史旧版 schema 的并发升级及长期重写入压力；本次验证针对正式运行暴露的当前 schema 初始化竞争。API Key 并发额度仍独立存在。
