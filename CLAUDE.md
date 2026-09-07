# Project Rules

## Authority and scope

- 产品、架构和技术栈分别以 PRODUCT.md、ARCHITECTURE.md、TECH_STACK.md 为准；调度遵循 CODEX_HANDOFF.md 和用户最新指令。
- MAIN 维护 ROADMAP，负责依赖、Scope、验收、集成和后续派发；Worker 不修改设计文档或 ROADMAP。
- MAIN 默认使用 gpt-5.6-terra 进行理解、拆解、调度、审查和验收；普通 Worker 请求 gpt-5.6-luna / max，使用最小完整 Task Brief。Luna 连续两轮验收失败后，由 Terra MAIN 分析；必要时才升级为 gpt-5.6-sol。GPT-6 不作为常驻调度模型。不得宣称未经验证的实际模型路由。
- 同时最多 3 个实现 Worker；依赖 DONE、任务 READY、文件范围独立才可并行。并行实现必须独立 feature branch + worktree。
- 连续两轮验收失败，停止重试并交 MAIN 分析；不得扩大范围。

## Task and worker organization

- 长期开发任务优先使用同一 Codex Project 中可见、可追踪的独立 Task / Thread，命名为 `TASK-XXX｜功能名称`。它应保留独立上下文，能回到同一 Worker 返工，并可绑定独立 branch + worktree。
- 当前工具环境若未暴露创建可见 Task / Thread 的能力，MAIN 必须先说明实际可用能力、侧边栏可见性、上下文持续性与 worktree 绑定能力，等待用户决定；不得把隐藏后台 subagent 假称为可见 Task / Thread，也不得用大量隐藏 subagent 替代长期 Worker。
- 后台 subagent 仅用于短时调查、资料搜索、报错分析或第二意见；需要写代码、多轮修改、返工、验收或独立 branch/worktree 的任务不使用后台 subagent。
- Worker 只读取完成当前 TASK 所需内容，只改 Task Brief 允许的文件，测试后报告 `READY_FOR_REVIEW` 或 `BLOCKED`。不得修改 ROADMAP、新增任务、扩张范围、无关重构、合并或自行进入下一 TASK。
- Worker 完成报告必须包含 TASK、STATUS、完成内容、修改文件、测试与结果、未解决问题、风险、Branch、Worktree、Commit 与验收步骤。MAIN 收到报告后自行核对 Task Brief、修改范围、git diff、测试、架构/接口约束、禁止项和 Acceptance Criteria；PASS 后直接完成正常提交、合并、ROADMAP 更新和依赖解锁，FAIL 后直接回到同一 Worker 返工。普通验收流程不逐步向用户申请批准。
- MAIN 持续推进所有依赖满足、范围清晰且互不冲突的后续任务。只有需求或架构存在关键歧义、明显超出范围、高风险或不可逆操作、新增外部账号/权限/付费、需要数据迁移、连续失败须改变技术路线，或存在重要业务方案待决定时，才暂停请求用户决定。
- MAIN 必须维护 Active Task ledger（Task ID、正式 Thread ID 或 clientThreadId、branch、worktree、验收状态）。Worker Completion Report 是首选信号，但不是唯一信号：每次收到项目工作、每次调度检查或自动心跳时，MAIN 都要核对可见 Task 状态及每个 Active worktree 的 `git status` / branch log。发现未报告的完成性变更时，MAIN 直接进入验收，不能把“没有正式 Thread ID”误判为“没有任务结果”。

## Directory contract

- 根目录：设计、规则、README、工程配置与无密钥配置模板。
- src/：源代码；config/：非敏感配置；tests/：测试及合成或明确获准公开的样本；scripts/：调度模板。
- data/raw/、data/notes/、data/knowledge/、data/index/：遵循现有架构的本地知识存储，全部排除出 Git。Raw 不可覆盖。
- runtime/：运行日志、缓存、临时文件与浏览器资料；图纸中 data/cache/、data/logs/ 为兼容预留，同样排除出 Git。
- output/：最终报告、导出物和交付物，默认排除出 Git。
- 文件名使用英文，文本使用 UTF-8；报告使用 TASK-ID-description.md。按需建目录，不提前创建空实现模块。
- 清理临时文件、删除文件和目录前必须获得用户明确确认。

## Safety and Git

- 不读取或记录密钥；不上传真实 PDF、微信资料、Raw、Notes、Knowledge、Index 或用户导出物。
- .env.example 仅存空值或非敏感示例；创建或修改真实 .env、密钥、CI/CD、系统配置、数据库迁移须先确认。
- 已验收 TASK 的正常短期 feature branch 创建、commit、fast-forward merge、ROADMAP 更新与依赖任务派发由 MAIN 自主完成，并在进度报告中说明。reset、rebase、force push、删除分支、改写历史、公开发布，以及其他不可逆 Git 操作仍须用户明确确认。
- 长期分支只有 main；不得建立长期 mac / windows 分支。
- TASK-001 尚无首次提交时，由单个 Worker 起草限定文件，MAIN 不同时编辑这些文件；不假称已有独立 worktree。

## Verification

- TASK-001：核对文件范围、Markdown 引用、配置模板无凭据；用 git check-ignore 验证私有路径被排除、工程文件可跟踪；检查 git status 和待提交内容。
- TASK-002 后按工程提供的 pytest / CLI 验收；当前不存在可运行应用，不宣称运行验证通过。
- 每个功能先用一个真实样本跑通最小闭环，再扩大样本；分别报告源码、依赖、打包、安装、运行、内容、格式、安全和回归结果，不适用项明确说明。
- Worker 必须返回 TASK、STATUS、完成内容、修改文件、测试与结果、未解决问题、风险、Branch、Worktree、Commit、验收步骤。
- TASK-000 是阅读确认任务，以用户确认作为完成条件，无代码合并要求；实现任务须 MAIN 验收 PASS 并完成正常集成后才 DONE。
