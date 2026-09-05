# Project Rules

## Authority and scope

- 产品、架构和技术栈分别以 PRODUCT.md、ARCHITECTURE.md、TECH_STACK.md 为准；调度遵循 CODEX_HANDOFF.md 和用户最新指令。
- MAIN 维护 ROADMAP，负责依赖、Scope、验收和合并建议；Worker 不修改设计文档或 ROADMAP。
- MAIN 默认使用 gpt-5.6-terra 进行理解、拆解、调度、审查和验收；普通 Worker 请求 gpt-5.6-luna / max，使用最小完整 Task Brief。不得宣称未经验证的实际模型路由。
- 同时最多 3 个实现 Worker；依赖 DONE、任务 READY、文件范围独立才可并行。并行实现必须独立 feature branch + worktree。
- 连续两轮验收失败，停止重试并交 MAIN 分析；不得扩大范围。

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
- commit、merge、reset、rebase、force push、删除分支和公开发布前，列出具体对象、范围和影响，获得用户确认。
- 长期分支只有 main；不得建立长期 mac / windows 分支。
- TASK-001 尚无首次提交时，由单个 Worker 起草限定文件，MAIN 不同时编辑这些文件；不假称已有独立 worktree。

## Verification

- TASK-001：核对文件范围、Markdown 引用、配置模板无凭据；用 git check-ignore 验证私有路径被排除、工程文件可跟踪；检查 git status 和待提交内容。
- TASK-002 后按工程提供的 pytest / CLI 验收；当前不存在可运行应用，不宣称运行验证通过。
- 每个功能先用一个真实样本跑通最小闭环，再扩大样本；分别报告源码、依赖、打包、安装、运行、内容、格式、安全和回归结果，不适用项明确说明。
- Worker 必须返回 TASK、STATUS、完成内容、修改文件、测试与结果、未解决问题、风险、Branch、Worktree、Commit、验收步骤。
- TASK-000 是阅读确认任务，以用户确认作为完成条件，无代码合并要求；实现任务须验收并获准合并后才 DONE。
