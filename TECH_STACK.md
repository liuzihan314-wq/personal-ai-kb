# Personal AI Knowledge Base — TECH_STACK.md

> Version: v0.2
> Status: V1 baseline approved；V2 multi-user design proposal（未实现）
> Based on: PRODUCT.md v0.2 / ARCHITECTURE.md v0.2

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
- V1 Retrieval：标题 / 标签 / 关键词 / Topic / Related / Index + 可选 embedding 语义召回；不使用向量数据库
- Vector DB：V1 不使用
- OCR：V1 不使用
- 云服务器：V1 不使用

### 2.1 V2 目标技术栈（规划，未实现）

| 层 | 目标选型 | 责任边界 |
| --- | --- | --- |
| 公共入口 | Cloudflare Access 自托管 Web 应用 | HTTPS、登录、显式 Allow／Block 策略；不负责应用内数据隔离 |
| 源站连接 | Cloudflare Tunnel／`cloudflared` | 通过出站连接把公开主机名转发到 CVM 本机服务；启用 Access JWT 校验；不把 Streamlit 端口公开 |
| 运行主机 | 腾讯云 CVM（Linux，具体镜像和规格待 TASK-032 确认） | 运行现有 Python／Streamlit、`cloudflared` 和持久化文件系统 |
| 应用身份层 | Python Auth Adapter + `IdentityContext` | 通过公开的 Streamlit `st.context.headers` 读取并校验 `Cf-Access-Jwt-Assertion`，解析 `iss`、`aud`、`exp`、`sub`，映射 `admin`／`member`；`user_id` 推荐为 `u_` + `sha256(iss + "\0" + sub)` |
| 用户存储 | 文件系统 `data/users/<user_id>/` | 按用户保存 Raw、Notes、Knowledge、Index、History 及用户内容型缓存／导出 |
| 业务层 | 现有 Core Services | 继续复用 Python、Streamlit、文件优先和可追溯知识链路 |
| 进程管理 | Linux `systemd`（目标方案） | 管理 Streamlit 与 `cloudflared` 的启动、重启和日志；部署任务再验证具体服务单元 |

V2 首期不新增数据库、消息队列、公开注册、跨用户共享或前后端分离工程。V1 的本地模式继续使用 `data/`，不能因为启用 V2 目标配置就自动迁移或覆盖现有数据。

已实现的无域名轻量分享模式使用 `PKB_AUTH_MODE=local` 和 `config/local_users.json`，认证成功后仍复用同一个 `UserScopedStorage`；它不替代 Cloudflare Access 的生产入口，仅用于低敏感朋友间分享。

JWT 的签名校验库在 TASK-028 实施时确定并锁定；本任务不安装依赖、不修改 `pyproject.toml`，也不把 Cloudflare team、audience、身份或角色值写入仓库。实现必须以官方 Access 证书端点校验签名，并拒绝缺失或不匹配的 `iss`／`aud`／`exp`／`sub`。

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

V2 首期同样不引入数据库：每个用户的 `Raw`、`Notes`、`Knowledge`、`Index` 和 `history` 都位于独立文件根目录。共享索引会破坏隔离，因此不作为 V2 首期优化手段；任何包含用户内容的缓存和导出也必须按用户命名空间保存。

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

V2 继续使用 Streamlit 作为应用入口，通过 Cloudflare Access 保护浏览器访问。UI 必须显示当前身份和角色，但不能显示完整认证头、密钥、服务器路径或其他用户的文件名；身份上下文由服务端注入 Core，不由页面控件传入。

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

V1 不上 Vector DB；当前允许在本地 JSON Index 之上使用可配置的 embedding 语义召回，不能把它升级成云端向量数据库或替换 Raw → Notes → Knowledge 主链路。

检索依据：

1. 标题
2. 标签
3. 关键词
4. Topic
5. Related
6. JSON Index
7. AI 对候选集合进行语义判断

保留 Retrieval 接口，后续如果几十到数百篇规模下真实效果不足，可调整 Hybrid／Embedding 的权重或缓存策略；不因此引入云端 Vector DB。

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

### V2 Tencent Cloud

- 用户浏览器访问 Cloudflare Access 的 HTTPS 主机名；Access 通过显式 Allow 策略控制谁可以到达应用。
- `cloudflared` 在腾讯云 CVM 建立出站 Tunnel，将请求转到仅监听本机的 Streamlit 服务；Tunnel 配置目标为 `originRequest.access.required=true` 和对应的 `audTag`，Tunnel 与服务状态都必须纳入健康检查。
- CVM 的数据目录使用持久化文件系统，部署前备份，重启后验证 Raw、Notes、Knowledge、Index 和 History 均可读取。
- 实例规格、地域、域名、身份提供商、备份目标和访问策略值待 TASK-032 确认；当前不提供生产命令，不写真实凭据。

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
- V2 Auth Adapter：缺失／伪造／过期 JWT、错误 issuer／audience、缺失 `sub`、未知／冲突角色和不可信身份头
- V2 Storage：A／B 的 Raw、Notes、Knowledge、Index、历史、来源和下载互不可见；路径穿越、空用户标识和存储失败不会回退到共享目录
- V2 deployment：Access 登录、Tunnel 转发、CVM 重启恢复、持久化目录和无身份拒绝

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

V2 首期也不采用：

- 公开注册和匿名访问
- 管理员默认读取成员内容或全局历史
- 共享全局 Index 或跨用户检索
- 把 Cloudflare Access 的登录通过等同于应用内授权
- 未备份的静默数据迁移

## 17. V2 官方能力依据

以下链接只用于核对目标架构，不表示本项目已经创建 Cloudflare 或腾讯云资源：

- [Cloudflare Access policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/)：自托管应用需要显式策略控制访问。
- [Cloudflare Access JWT validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/)：应用应校验 `Cf-Access-Jwt-Assertion` 的签名。
- [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/)：通过出站连接把源站服务发布到公开主机名，无需开放源站入站端口。
- [腾讯云 CVM 文档](https://cloud.tencent.com/document/product/213)：CVM 提供运行应用所需的计算、存储和网络资源。
- [Streamlit `st.context`](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.context)：通过公开 API 读取当前请求的只读 headers，不依赖私有 WebSocket API。
