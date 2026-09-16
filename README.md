# Personal AI Knowledge Base

一个面向个人使用的 AI 内容知识库：把微信公众号文章、文本 PDF 和自己的观点卡片沉淀为可检索、可追溯的知识，并用于主题综合、AI 提效选题和 2～3 分钟口播稿生成。

## 当前状态

当前已提供可运行的 Streamlit MVP。它把 PDF、观点卡片、Search / Q&A、主题综合、选题和口播放在同一个日常入口，页面只调用已有 Core Services。

## 启动 Web UI

```bash
uv sync
uv run streamlit run src/pkb/ui/app.py
```

- 目的：同步项目依赖并启动本地 Streamlit 页面。
- 预期：浏览器打开本地页面后，可依次完成资料导入、观点卡片、检索 / 问答、主题综合、明确选择选题和口播生成。
- 失败后：先确认当前目录是项目根目录且 Python 满足 `pyproject.toml` 的版本要求；若提示数据不存在，先通过页面导入一个文本型 PDF 或保存一张观点卡片。

## 配置真实 AI 回答

页面不会再把测试用的 Mock 输出当作回答。未配置 Provider 时，问答会保留本地证据和来源，但会明确提示尚未生成语义回答。

也可以直接在页面左侧填写 DeepSeek 与向量模型配置，再点击保存。网页会将配置保存在项目根目录的本机 `.env`，之后启动网页时自动加载，无需重复输入。保存时 `.env` 会限制为当前系统用户可读写；密钥不显示、不写日志，也不会提交到 Git。

复制 `.env.example` 为本机 `.env`，填入自己的 DeepSeek API Key 后重启 Streamlit：

```dotenv
PKB_AI_PROVIDER=deepseek
PKB_AI_MODEL=deepseek-v4-flash
PKB_AI_BASE_URL=https://api.deepseek.com
PKB_AI_API_KEY=your-secret-key

# 可选：配置后启用向量语义检索；三项留空则使用直接检索
PKB_EMBEDDING_MODEL=qwen3.7-text-embedding-flash
PKB_EMBEDDING_BASE_URL=https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
PKB_EMBEDDING_API_KEY=your-embedding-secret-key
```

- 目的：让导入、主题综合、问答和口播通过 OpenAI-compatible `chat/completions` 接口使用真实模型，同时回答仍只传入本地检索出的证据。
- 预期：重启电脑或页面后，网页自动读取已保存配置；“生成回答”会给出中文回答与来源链，配置向量模型后会启用语义召回。
- 失败后：先确认 `.env` 位于项目根目录、四个变量均非空并重启页面；若服务端返回 HTTP 错误，核对 API Key、账户余额、模型名和 endpoint。不要把 `.env` 或 API Key 提交到 Git。

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
