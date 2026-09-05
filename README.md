# Personal AI Knowledge Base

一个面向个人使用的 AI 内容知识库：把微信公众号文章、文本 PDF 和自己的观点卡片沉淀为可检索、可追溯的知识，并用于主题综合、AI 提效选题和 2～3 分钟口播稿生成。

## 当前状态

项目目前处于仓库基础准备阶段。产品、架构和技术栈已经确认，但应用代码、依赖和 CLI / Web UI 尚未建立，因此当前不可运行。后续实现应先完成一个真实样本的最小闭环，再扩展输入和输出范围。

## 已批准技术栈

- 运行环境：macOS 为主，Windows 作为备用兼容环境
- 语言与环境：Python 3.12、`pyproject.toml`、`uv`
- 存储：本地文件系统；Notes / Knowledge 使用 Markdown + YAML Frontmatter；Index 使用 JSON
- 输入与界面：PyMuPDF（文本 PDF）、Typer（CLI）、Streamlit（Web UI）
- 配置与质量：`.env` + pydantic-settings、Python logging、pytest
- 调度：macOS `launchd`；Windows Task Scheduler adapter
- AI：可插拔 Provider abstraction；V1 不使用向量数据库、OCR、云服务器

## 设计文档

- [PRODUCT.md](PRODUCT.md)：产品范围、输入、输出与数据原则
- [ARCHITECTURE.md](ARCHITECTURE.md)：数据流、分层与模块边界
- [TECH_STACK.md](TECH_STACK.md)：技术选型与适用范围
- [ROADMAP.md](ROADMAP.md)：任务依赖、验收标准与里程碑
- [CODEX_HANDOFF.md](CODEX_HANDOFF.md)：MAIN / Worker 协作和 Git 约定

## 目录约定

| 路径 | 用途 | Git 策略 |
| --- | --- | --- |
| 根目录 | 设计文档、规则、README、工程配置和无密钥模板 | 跟踪 |
| `src/` | 源代码；核心业务与平台 Adapter 分离 | 跟踪 |
| `config/` | 非敏感配置 | 跟踪 |
| `tests/` | 测试及获准使用的合成样本 | 跟踪 |
| `scripts/` | 调度与运维模板 | 跟踪 |
| `data/raw/` | 不可覆盖的原始资料 | 排除 |
| `data/notes/` | 单篇 AI 理解结果 | 排除 |
| `data/knowledge/` | 多篇资料编译的主题知识 | 排除 |
| `data/index/` | 本地检索索引 | 排除 |
| `data/cache/`、`data/logs/` | 兼容预留的缓存与日志 | 排除 |
| `runtime/` | 日志、缓存、临时文件和浏览器资料 | 排除 |
| `output/` | 报告、导出物和交付物 | 排除 |

`data/` 下的所有内容都属于本地知识存储，不能上传到 GitHub；`Raw` 是事实来源，AI 生成的 `Notes` 和 `Knowledge` 必须与它分开并保留来源追踪。目录按任务需要创建，不提前生成空实现模块。

## Git 基础操作

以下命令用于理解和检查仓库状态。`commit`、`merge`、`reset`、`rebase`、分支删除和 `push` 会改变项目状态或历史，执行前应先确认目标和影响。

### 查看状态

```bash
git status --short --branch
```

- 目的：查看当前分支，以及已修改、已暂存和未跟踪的文件。
- 预期：能看到分支名和工作区文件状态；未确认的个人资料应保持未加入暂存区。
- 失败后：若提示不是 Git 仓库，先回到项目根目录；若出现意外文件，先检查路径和 `.gitignore`，不要直接 `git add .`。

### 查看差异

```bash
git diff
```

- 目的：查看已跟踪文件的未暂存改动。
- 预期：显示逐行变更；首次创建的未跟踪文件不会出现在普通 `git diff` 中，应先用 `git status` 确认，或在暂存后使用 `git diff --cached`。
- 失败后：若输出为空，确认文件是否为未跟踪状态；若差异超出预期，停止暂存并回到对应文件检查。

### 暂存并复核

```bash
git add README.md .gitignore .env.example
git diff --cached
```

- 目的：只把本次仓库基础文件放入下一次提交，并在提交前复核内容。
- 预期：缓存区只包含这三个文件，且没有 `.env`、`data/`、`runtime/` 或 `output/` 中的私人内容。
- 失败后：若出现额外文件，停止操作并把意外暂存路径报告给 MAIN；列出具体的取消暂存方案并获得明确批准后再处理，未获批准前不要执行任何回滚命令。

### 创建提交

```bash
git commit -m "chore: add repository foundation"
```

- 目的：把已经复核的暂存内容记录为一个可追溯的本地版本。
- 预期：生成新的本地 commit，提交后 `git status` 显示工作区干净或只剩明确未跟踪文件。
- 失败后：若提示 Git 身份未配置，先按本机 Git 配置流程处理；若检查或 hook 失败，阅读完整错误并修复原因后再提交，不要绕过检查。

### 推送到远端

```bash
git push -u origin main
```

- 目的：将本地 `main` 的已确认提交上传到 GitHub 私有仓库，并建立上游跟踪关系。
- 预期：远端私有仓库出现相同的设计文档和基础文件，私人数据与凭据没有上传。
- 失败后：若 `origin` 不存在或仓库不是 Private，由 MAIN 先核对远端配置和仓库权限；若认证或推送被拒绝，检查账号权限与远端状态，禁止用 force push 绕过问题。
