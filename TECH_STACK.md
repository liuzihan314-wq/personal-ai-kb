# Personal AI Knowledge Base — TECH_STACK.md

> Version: v0.1  
> Status: Approved draft for Codex handoff  
> Based on: PRODUCT.md / ARCHITECTURE.md

## 1. 选型原则

优先：

- 主流
- 简单
- 本地
- 文件优先
- AI / Codex 熟悉
- 少组件、少运维
- 先跑通 MVP，再按实际问题升级

核心分工：

**机械工作交脚本，语义工作交 AI。**

---

## 2. V1 技术栈

- 主运行环境：macOS
- 兼容目标：Windows backup runtime
- 主语言：Python 3.12
- 项目配置：`pyproject.toml`
- Python 依赖 / 环境：`uv`
- 版本控制：Git
- 远程托管：GitHub Private Repository
- 主体存储：本地文件系统
- Notes / Knowledge：Markdown + YAML Frontmatter
- Index：JSON
- PDF 文本提取：PyMuPDF
- CLI：Typer
- Web UI：Streamlit
- 配置：`.env` + pydantic-settings
- 测试：pytest
- 日志：Python logging
- macOS 定时任务：launchd
- Windows 定时任务：Task Scheduler adapter（备用）
- AI：Provider abstraction，可插拔
- V1 Retrieval：标题 / 标签 / 关键词 / Topic / Related / Index + AI 候选判断
- Vector DB：V1 不使用
- OCR：V1 不使用
- 云服务器：V1 不使用

---

## 3. 为什么用 Python

原因：

- AI / Codex 熟悉
- 文件处理、PDF、CLI、本地自动化生态完整
- 非程序员项目容易理解
- 适合 Mac 和 Windows
- 能减少前后端技术分裂

---

## 4. 为什么文件优先

主体数据放在：

- `data/raw/`
- `data/notes/`
- `data/knowledge/`
- `data/index/`

优势：

- 人可以直接打开
- AI 可以直接读取
- 易备份
- 易调试
- 少运维
- 错误更容易追溯

V1 不把 MySQL / PostgreSQL / MongoDB 作为主体存储。

后续如果实际需要，可引入 SQLite 作为辅助索引，而不迁移 Raw / Notes / Knowledge 的核心事实文件。

---

## 5. 推荐目录

```text
personal-ai-kb/
├── PRODUCT.md
├── ARCHITECTURE.md
├── TECH_STACK.md
├── ROADMAP.md
├── CODEX_HANDOFF.md
├── README.md
├── pyproject.toml
├── .gitignore
├── .env.example
│
├── src/
│   └── pkb/
│       ├── core/
│       │   ├── document.py
│       │   ├── ingest.py
│       │   ├── notes.py
│       │   ├── compiler.py
│       │   ├── retrieval.py
│       │   ├── topics.py
│       │   ├── script_writer.py
│       │   └── services.py
│       │
│       ├── adapters/
│       │   ├── pdf/
│       │   ├── ideas/
│       │   ├── wechat/
│       │   ├── ai/
│       │   └── platform/
│       │
│       ├── ui/
│       ├── cli/
│       ├── index/
│       ├── utils/
│       └── config.py
│
├── tests/
│
├── data/
│   ├── raw/
│   ├── notes/
│   ├── knowledge/
│   ├── index/
│   ├── cache/
│   └── logs/
│
└── scripts/
```

---

## 6. PDF

库：PyMuPDF。

V1 只处理正常文本 PDF。

不实现：

- OCR
- 扫描件识别
- 图片型 PDF 转文本

---

## 7. Web UI

V1 使用 Streamlit。

目的：

- 快速得到可用界面
- 上传 PDF
- 添加观点卡片
- 搜索 / 问答
- 主题综合
- 选题
- 口播

V1 不做 React + 独立后端等重型前后端架构。

---

## 8. CLI

V1 使用 Typer。

示例：

```bash
pkb import-pdf xxx.pdf
pkb add-idea
pkb import-wechat-article
pkb sync-wechat  # Experimental / POC
pkb search "AI视频"
pkb generate-topics
pkb write-script
```

CLI 用于自动化、调试、验收和定时任务，不是主要日常 UI。

---

## 9. AI Provider

核心不得写死某个模型。

统一接口示意：

- summarize
- extract_key_points
- extract_quotes
- generate_tags
- compile_topic
- answer
- generate_topics
- write_script

### 开发阶段

Codex 主要承担：

- 编码
- 调试
- 测试
- 设计对齐
- Git / worktree 协助

### 程序自动化阶段

如果需要无人值守 AI 加工，使用可配置的 API Provider。

用户倾向 DeepSeek，因此优先实现一个 DeepSeek-compatible provider，但：

- 不把具体模型名写死在核心代码
- model / base_url / key 从配置读取
- 后续可以替换其他 Provider

---

## 10. Retrieval

V1 不上 Vector DB。

检索依据：

1. 标题
2. 标签
3. 关键词
4. Topic
5. Related
6. JSON Index
7. AI 对候选集合进行语义判断

保留 Retrieval 接口，后续如果几十到数百篇规模下真实效果不足，再增加 Hybrid / Embedding。

---

## 11. 微信输入

### Manual WeChat Article Import

状态：V1 MUST HAVE。

- Web UI 与 CLI 共用 Core Service
- 仅允许微信公众号文章 URL
- 自动提取失败时允许标题、正文和原始 URL 手动提交
- 输出既有 UnifiedDocument，并写入 immutable Raw
- 不为该入口修改 Notes / Knowledge / Index / Retrieval 公共接口

### Favorites Auto Sync

- macOS：`BLOCKED POC`
- Windows：`POC CANDIDATE / NOT VERIFIED`

POC 只验证：

1. macOS 能否稳定读取收藏新增
2. 能否识别微信公众号文章
3. 能否提取正文 / 来源
4. 能否去重
5. 能否过滤视频与普通 URL
6. 微信升级 / 重启后的稳定性

Manual 与 Favorites Adapter 都必须与 Core 解耦。Favorites POC 失败不能阻塞 V1。

---

## 12. macOS / Windows

### macOS

- 当前主开发
- 当前主运行
- Manual WeChat Article Import 是 V1 稳定入口
- WeChat macOS Favorites POC 当前为 `BLOCKED`
- 定时任务使用 launchd

### Windows

- 备用运行
- Core 需要避免无必要的 macOS 专属代码
- Scheduler 通过 Windows adapter 接 Task Scheduler
- Windows WeChat Favorites Adapter 属后续 POC，当前未验证
- 不为 OS 建长期 Git 分支

---

## 13. Git / GitHub

### Git

用于：

- status
- diff
- commit
- branch
- merge
- worktree

### GitHub

创建 Private Repository 保存代码和设计文档。

上传：

- 源代码
- 测试
- 文档
- 配置模板

不上传：

- `.env`
- API Key
- 微信收藏原文
- 私人 PDF
- 真实 `data/raw/`
- 真实 Notes / Knowledge 数据

`.gitignore` 至少覆盖：

```gitignore
.env
.DS_Store
__pycache__/
.venv/
data/raw/
data/notes/
data/knowledge/
data/cache/
data/logs/
```

---

## 14. 分支 / Worktree

长期稳定分支：

- `main`

功能分支示例：

- `feat/project-foundation`
- `feat/pdf-ingest`
- `feat/idea-card`
- `feat/ai-notes`
- `feat/retrieval`
- `feat/topic-generator`
- `feat/script-writer`
- `feat/wechat-macos`
- `feat/web-ui`
- 任务期间可使用短期 `poc/wechat-windows`

并行 Worker 修改代码时，使用独立 worktree。

不使用长期：

- `mac`
- `windows`

环境分支。

---

## 15. 测试

使用 pytest。

最低测试范围：

- PDF 导入
- Idea Card
- Raw 不覆盖
- Note 结构
- Related
- Knowledge 编译
- Retrieval
- Topics
- Script
- Manual WeChat Article URL 白名单、Raw immutable 与去重
- Favorites POC 的真实公众号文章、视频和普通 URL 分类证据
- macOS / Windows 路径兼容的核心 smoke test

---

## 16. V1 暂不采用

- Vector DB
- 大型 RAG 框架
- OCR
- Docker 强依赖
- 云服务器
- 消息队列
- 用户系统
- 前后端分离大工程
- 小红书 / YouTube 自动读取
- 自动视频生成 / 剪辑 / 发布
