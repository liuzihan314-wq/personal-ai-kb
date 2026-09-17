# Personal AI Knowledge Base — ROADMAP.md

> Version: v0.2
> Owner: MAIN Coordinator only
> Rule: Worker Agents may read this file but must not edit task status, dependencies, ownership or milestones.

## 1. 目标

把 PRODUCT.md、ARCHITECTURE.md、TECH_STACK.md 转为可执行任务。

原则：

- 小步开发
- 明确依赖
- 能并行的任务由不同 Worker 并行
- 同一 Codex Project 下开独立 Task thread
- 并行改代码时使用独立 branch + worktree
- Worker 完成后回报 MAIN
- MAIN 验收通过后才进入合并 / 下一任务
- 不通过则返回原 Worker 修复
- `main` 保持稳定

---

## 2. 状态定义

- `BLOCKED`：依赖未满足
- `READY`：可以分配
- `IN_PROGRESS`：Worker 正在执行
- `REVIEW`：等待 MAIN 验收
- `DONE`：验收通过并完成合并
- `POC_REQUIRED`：依赖满足后可作为独立可行性任务派发；只能验证，不能假定方案已成立

---

## 3. Milestone 总览

```mermaid
flowchart TD
    M0[M0 Project Foundation]
    M1[M1 Input Foundation]
    M2[M2 AI Notes]
    M3[M3 Retrieval & Knowledge]
    M4[M4 Content Creation]
    M5[M5 WeChat Input and Favorites POC]
    M6[M6 Web UI]
    M7[M7 Cross-platform Hardening]
    M8[M8 V2 Multi-user Access]
    M9[M9 GitHub Presentation]

    M0 --> M1
    M1 --> M2
    M2 --> M3
    M3 --> M4
    M1 --> M5
    M4 --> M6
    M5 -.Favorites POC 非阻塞.-> M6
    M6 --> M7
    M6 --> M8
    M6 --> M9
```

---

# M0 — Project Foundation

## TASK-000 — Read Design Docs and Restate

Status: DONE
Dependencies: none  
Owner: MAIN

Acceptance record: 2026-09-06 用户确认项目理解并授权开始执行；此任务仅阅读复述，无实现代码需要合并。

Codex must first read:

- PRODUCT.md
- ARCHITECTURE.md
- TECH_STACK.md
- ROADMAP.md
- CODEX_HANDOFF.md

Output:

- 用自己的话复述产品目标
- V1 输入 / 输出
- V1 不做什么
- Raw / Notes / Knowledge / Index 区别
- macOS / Windows 边界
- 当前最大风险
- 不写代码

Acceptance:

- 用户确认 Codex 理解正确

---

## TASK-001 — Git + Repository Foundation

Status: DONE  
Dependencies: TASK-000

Owner: MAIN（Git / GitHub / 验收）+ TASK-001 Worker（README / 忽略规则 / 无密钥模板）

Progress: 2026-09-07 本地 main 已初始化，基础文件子范围经 MAIN 复核 PASS；首次提交 27fd0b1 已推送至已核验的 GitHub Private Repository，远端 main 与本地一致。TASK-001 完整验收通过。

Scope:

- 初始化本地 Git repo（如果尚未初始化）
- 准备 `.gitignore`
- 准备 `.env.example`
- 准备基础 README
- 如果 GitHub 私有仓库尚不存在，协助用户创建 `Private Repository`
- 绑定 remote
- 首次 push 前确保私人数据未进入 Git

Acceptance:

- `git status` 清晰
- GitHub repo 为 Private
- 设计文档与基础工程文件可在 GitHub 看到
- `.env` / 私人知识数据没有上传
- 用户理解 `status / diff / commit / push` 的基本作用

---

## TASK-002 — Python Project Skeleton

Status: DONE
Dependencies: TASK-001

Branch:

`feat/project-foundation`

Acceptance record: 2026-09-07 MAIN verified the allowed diff, `uv sync`, sdist/wheel build, `pytest` (7 passed), `pkb health`, `pkb hello`, warning-free CLI execution, cross-platform `pathlib` use, and absence of macOS-only APIs, OCR, vector databases, credentials, and `/Users` hardcodes. Integrated to local `main` as `0d4e040`.

Scope:

- `pyproject.toml`
- uv environment
- `src/pkb/`
- `tests/`
- `data/` 空目录约定
- 基础 config
- 基础 logging
- CLI hello / health check

Acceptance:

- macOS 可安装依赖
- `pytest` 可运行
- CLI health command 可运行
- Core 不依赖 macOS 专属 API
- Windows 路径处理使用跨平台方式（如 pathlib）

---

# M1 — Input Foundation

TASK-003 与 TASK-004 在 TASK-002 后可并行。

```mermaid
flowchart LR
    T2[TASK-002 Foundation]
    T3[TASK-003 PDF]
    T4[TASK-004 Idea Card]
    T2 --> T3
    T2 --> T4
```

## TASK-003 — PDF Import

Status: DONE
Dependencies: TASK-002  
Suggested branch: `feat/pdf-ingest`

Acceptance record: 2026-09-07 MAIN verified allowed scope, immutable Raw storage, deduplication, text-PDF import, scan rejection without OCR, `uv lock --check`, sdist/wheel build, `pytest` (11 passed), and CLI health/hello. PyMuPDF emits five upstream SWIG deprecation warnings under pytest; ordinary V1 test execution passes, while warnings-as-errors is not currently supported by that dependency.

Scope:

- 文本 PDF 导入
- PyMuPDF 文本提取
- UnifiedDocument
- Raw 保存
- metadata
- 去重基础

Not in scope:

- OCR
- 扫描 PDF

Acceptance:

- 文本 PDF 可导入
- 原 PDF 保留
- 提取文本可读
- 重复导入不会产生重复记录
- 扫描 PDF 给出明确“不支持”提示而不是 OCR

---

## TASK-004 — Idea / Quote Card

Status: DONE
Dependencies: TASK-002, TASK-003（UnifiedDocument / Raw interface）
Suggested branch: `feat/idea-card`

Acceptance record: 2026-09-07 MAIN verified immutable UTF-8 idea-card Raw records, optional source/tags/note, duplicate idempotence, PDF Raw regression, CLI add-idea execution, and full `pytest` (17 passed). The existing upstream PyMuPDF/SWIG warning remains tracked under TASK-003.

Scope:

- 手动观点
- 好句
- 灵感
- 用户判断

Acceptance:

- 可创建卡片
- 可保存 optional source / tags / note
- 进入统一 Document / Raw 结构
- 可被后续 Retrieval 使用

---

# M2 — AI Notes

## TASK-005 — AI Provider Interface

Status: DONE
Dependencies: TASK-002  
Suggested branch: `feat/ai-provider`

Acceptance record: 2026-09-07 MAIN verified vendor-neutral interface, network-free mock provider, environment-loaded and masked secret configuration, `pytest` (9 passed), and CLI health/hello. Integrated to local main in `fbdd403`.

Scope:

定义可插拔 Provider interface。

不把模型名 / API Key 写死。

Acceptance:

- mock provider 可用于测试
- provider config 可从环境读取
- Core 不依赖特定厂商 SDK

---

## TASK-006 — Single-document AI Notes

Status: DONE
Dependencies: TASK-003, TASK-004, TASK-005  
Suggested branch: `feat/ai-notes`

Acceptance record: 2026-09-07 MAIN verified five synthetic document Notes, PDF and idea rendering, YAML frontmatter, Raw non-overwrite, Note duplicate idempotence, MockAIProvider-only processing, CLI generation, `uv sync`, and `pytest` (22 passed). The existing upstream PyMuPDF/SWIG warning remains tracked under TASK-003.

Scope:

- summary
- key points
- quotes
- tags
- source references
- Markdown + frontmatter

Acceptance:

- 5 篇测试资料均可产生合法 Note
- Note 不覆盖 Raw
- Note 可以定位回 source
- 观点卡片不被强制套用不合理的长文摘要模板

---

# M3 — Retrieval & Knowledge

TASK-007 与 TASK-008 部分可在共同基础完成后拆 Worker，但 MAIN 应控制文件边界。

## TASK-007 — Index + Related

Status: DONE
Dependencies: TASK-006  
Suggested branch: `feat/index-related`

Acceptance record: 2026-09-07 MAIN verified local JSON rebuild/read, explainable symmetric Related links, no false relation for unrelated Notes, non-mutating Note rebuilds, corrupt-input errors, `uv sync`, `pytest` (27 passed), and CLI index rebuild/status. The existing upstream PyMuPDF/SWIG warning remains tracked under TASK-003.

Scope:

- JSON index
- title / tags / keywords / topic
- related rule scoring
- 双向 related
- 可解释日志

Acceptance:

- 新 Note 可进入 Index
- 相关文档能建立关联
- 关联理由可解释
- Index 可重建
- 不依赖向量库

---

## TASK-008 — Retrieval Service

Status: DONE
Dependencies: TASK-007  
Suggested branch: `feat/retrieval`

Acceptance record: 2026-09-07 MAIN verified the allowed scope, read-only local Index retrieval, deterministic and explainable title/tag/keyword/topic/Related ranking, source paths, clear no-match results, CLI search, no vector database or network use, branch-level tests (5 passed), and merged-main regression (38 passed). The existing upstream PyMuPDF/SWIG warning remains tracked under TASK-003.

Scope:

- title
- tags
- keywords
- topic
- related
- candidate ranking
- AI candidate judgment interface

Acceptance:

- 对测试问题可以找到合理候选
- 返回来源路径
- 没命中时明确告诉调用方
- 不静默调用向量数据库

---

## TASK-009 — Knowledge Compiler

Status: DONE
Dependencies: TASK-006, TASK-007  
Suggested branch: `feat/knowledge-compiler`

Acceptance record: 2026-09-07 MAIN verified the allowed scope, traceable Topic Knowledge compilation from Notes, source links back through Notes to Raw, safe replacement when a topic gains material, Raw/Notes/Index read-only behavior, Mock provider use, branch-level tests (6 passed), and merged-main regression (38 passed). The existing upstream PyMuPDF/SWIG warning remains tracked under TASK-003.

Scope:

- 多 Note → Topic Knowledge
- source trace
- 更新已有 Topic
- 不修改 Raw

Acceptance:

- 5 篇相关资料可编译成一个主题页
- Knowledge 能追踪到 Notes
- Notes 能追踪到 Raw
- 新资料加入后可更新主题页

---

# M4 — Content Creation

## TASK-010 — Q&A / Topic Synthesis

Status: DONE
Dependencies: TASK-008, TASK-009  
Suggested branch: `feat/qa`

Acceptance record: 2026-09-08 MAIN discovered unreported worker changes through the Active Task worktree scan, then verified allowed scope, local-only Knowledge/Notes/Raw evidence chains, structured no-hit and insufficient-evidence states, deterministic Mock-provider test coverage, CLI output, no vector database or network use, branch-level tests (45 passed), and merged-main regression (49 passed). The existing upstream PyMuPDF/SWIG warning remains tracked under TASK-003.

Acceptance:

- “AI 视频有哪些思路？”类问题可基于库内知识回答
- 结果能给出对应来源
- Knowledge 不足时可沿 Notes / Raw 补充

---

## TASK-011 — Topic Generator

Status: DONE
Dependencies: TASK-008, TASK-009  
Suggested branch: `feat/topic-generator`

Acceptance record: 2026-09-08 MAIN discovered unreported worker changes through the Active Task worktree scan, then verified allowed scope, 3–5 explainable local candidates, explicit moderate recency rule, idea-card evidence, source traceability, insufficient-data results without invented candidates, CLI output, no vector database or network use, branch-level tests (42 passed), and merged-main regression (49 passed). The existing upstream PyMuPDF/SWIG warning remains tracked under TASK-003. The concurrent CLI conflict was resolved by MAIN by retaining both independent commands, then tested on merged main.

Scope:

- 全库候选
- 近期资料适当加权
- 观点卡片参与
- 输出 3～5 个候选

Acceptance:

- 不只是重写最近标题
- 每个选题说明为什么值得做
- 每个选题可回溯到支持它的知识 / Notes

---

## TASK-012 — Script Writer

Status: DONE
Dependencies: TASK-011, TASK-008  
Suggested branch: `feat/script-writer`

Acceptance record: 2026-09-08 MAIN discovered unreported worker changes through the Active Task worktree scan, then verified explicit human-confirmation gating, fresh Retrieval on every confirmed request, 2–3 minute bounded Chinese script output, traceable Knowledge/Notes/Raw evidence, no-evidence results without fabrication, deterministic Mock-provider coverage, CLI output, no vector database or network use, branch-level tests (53 passed), and merged-main regression (53 passed). The existing upstream PyMuPDF/SWIG warning remains tracked under TASK-003.

Flow:

选题  
→ 用户选择  
→ Retrieval  
→ 证据上下文  
→ 2～3 分钟口播

Acceptance:

- 未经“用户选题”不自动继续
- 生成前重新检索证据
- 口播可追溯到使用的知识来源
- 内容自然、具体、避免纯鸡汤

---

# M5 — WeChat Input and Favorites POC

## TASK-013 — macOS WeChat Favorites Feasibility POC

Status: BLOCKED
Dependencies: TASK-002  
Suggested branch: `poc/task-013-wechat-macos`

Progress: 2026-09-15 MAIN accepted the POC as technically BLOCKED, not functionally complete. Synthetic metadata classification and filtering tests pass (8 POC tests), and real read-only observation confirmed that `favorite.db` / `favorite_fts.db` change after collection activity. The files have no standard SQLite header and cannot be opened by SQLite read-only mode. No safe real-client evidence established item enumeration, official-account classification, title/body/source extraction, stable item identity, deduplication, real video/URL filtering, or restart-safe synchronization. Current runnable macOS 4.x references require database unlock, copied snapshots, process key capture, SIP/debug permissions, or content-level UI capture; those operations remain outside the approved boundary. Do not merge this branch as a completed sync solution or enter TASK-014.

Important:

这是 POC，不得一开始假定技术路线稳定。

Scope:

- macOS 微信收藏本地数据可行性
- 新增项识别
- 微信公众号文章白名单
- 文章 metadata / 正文
- 去重
- 视频 / 普通 URL 过滤

Acceptance:

1. 收藏一篇公众号文章后可检测
2. 可确认属于公众号文章
3. 可得到足够的标题 / 正文 / 来源
4. 第二次同步不重复
5. 收藏视频不会进入
6. 普通 URL 不会进入
7. 微信重启后仍可再次执行
8. 把版本 / 加密 / 数据路径等不确定性记录下来

Failure rule:

若 POC 不稳定：

- 不阻塞 PDF / Idea / Notes / Retrieval / Topics / Script
- 保留手动公众号导入兜底
- MAIN 决定是否延期、换实现或降级

---

## TASK-014 — macOS Favorites Auto Sync Productionization

Status: BLOCKED  
Dependencies: TASK-013 PASS, TASK-003, TASK-004（input foundation stable）
Suggested branch: `feat/wechat-macos`

Acceptance:

- 接入 UnifiedDocument
- 自动去重
- 白名单稳定
- 可由 CLI 调用
- 失败有日志
- 不影响 Core

---

## TASK-015 — macOS Favorites Scheduler

Status: BLOCKED  
Dependencies: TASK-014  
Suggested branch: `feat/macos-scheduler`

Scope:

- launchd
- 每日运行 sync command
- 日志
- 手动触发

Acceptance:

- 可重复执行
- 机器重启后配置仍有效
- 失败不会破坏已有知识

---

# M6 — Web UI

## TASK-026 — Manual WeChat Article Import

Status: DONE
Dependencies: TASK-003, TASK-016
Suggested branch: `feat/manual-wechat-article`

Acceptance record: 2026-09-15 MAIN verified the URL allow-list, immutable text Raw storage, normalized-URL deduplication, CLI/UI shared Core Service, manual fallback, Note/Index persistence and PDF/Idea regression. The public-article end-to-end slice used a temporary data directory and produced article Raw, Note and Index without recording article content in Git. HTTPS validation uses certifi's CA bundle; public fetches send a minimal mobile WeChat compatibility User-Agent and Chinese language header, without Cookie, login state, proxy, device fingerprint, CAPTCHA bypass or database access. Targeted tests passed (11); full regression passed (90), with the existing PyMuPDF/SWIG warnings only.

Goal:

为 V1 提供可靠的微信公众号文章输入入口，不依赖微信收藏数据库。

Scope:

- Web UI 与 CLI 共用同一 Core Service
- 仅接受明确的微信公众号文章 URL
- 自动提取成功时生成既有 UnifiedDocument
- 自动提取失败时返回 `manual_required`，允许用户补充标题、正文和原始 URL
- 使用 `content_type=article`、`source_type=wechat` 和 metadata 中的 manual ingest 标记
- 仅对 RawStorage 增加向后兼容的 article 文本路径支持，保持现有 `store` / `load_document` / `paths_for` 调用契约及 PDF / Idea 路径不变
- Raw immutable、重复导入幂等

Not in scope:

- 修改 UnifiedDocument、Notes、Knowledge、Index、Retrieval 或 Provider 公共接口
- macOS / Windows Favorites 自动同步
- 普通网页、视频、视频号、短链接或其他微信内容导入
- Cookie、登录态、代理证书、OCR 或数据库解密

Acceptance:

1. 接受合法 `https://mp.weixin.qq.com/s/...` 文章 URL
2. 拒绝普通网页 URL、视频号及其他不受支持的微信链接，且不产生 Raw
3. 自动提取成功时生成现有 UnifiedDocument；失败时不写残缺 Raw，并明确要求手动正文
4. 用户提交非空标题、正文和原始公众号 URL 后可完成导入
5. article 使用文本型 Raw 保存，重启后可读取，且不改变现有 PDF / Idea 存储行为
6. 同一规范化 URL 重复导入不新增、不覆盖原 Raw
7. 成功导入可继续生成 Note 并更新 Index
8. UI 与 CLI 不复制解析、白名单或去重逻辑
9. 使用一篇真实公众号文章完成最小端到端验收
10. 真实正文、Cookie、凭据和私人数据不进入测试、日志或 Git
11. 手动导入失败不影响 PDF、Idea、Notes、Knowledge、Retrieval、Topics 或 Script
12. 全量回归测试通过

---

## TASK-016 — Streamlit MVP

Status: DONE
Dependencies: TASK-010, TASK-011, TASK-012  
Suggested branch: `feat/web-ui`

Acceptance record: 2026-09-08 MAIN discovered unreported worker changes through the Active Task worktree scan, then verified that the single-page UI delegates to existing Core Services, preserves explicit topic confirmation before Script Writer, supports the V1 daily flow, includes the required project-local Streamlit dependency and lock update, performs PDF/idea minimum vertical slices, and contains UI tests. The system did not provide `uv`; MAIN bootstrapped it only in the Task worktree's local `.venv`, ran `uv sync --locked`, verified Streamlit 1.63.0 import, then ran merged-main regression (60 passed). The existing upstream PyMuPDF/SWIG warning remains tracked under TASK-003.

UI 最少包含：

- PDF import
- Idea card
- Search / Q&A
- Topic synthesis
- Generate topics
- Select topic
- Generate script

Acceptance:

- 主要日常流程不需要 CLI
- UI 只调用 Core，不复制业务逻辑

---

## TASK-020 — UI Visual Redesign

Status: DONE
Dependencies: TASK-016
Suggested branch: `feat/ui-visual-redesign`

Acceptance record: 2026-09-08 MAIN verified the allowed UI-only scope, no new dependencies or external assets, retained Core-service delegation and explicit script-confirmation gate, narrow-screen and desktop rendering against the user-provided visual reference, and full merged-main regression (61 passed). The visual system uses original CSS gradients and shapes rather than reference-image content. The existing upstream PyMuPDF/SWIG warning remains tracked under TASK-003.

Scope:

- 以用户提供的移动端卡片参考图为视觉参考，重做 Streamlit MVP 的布局、色彩、信息层级与响应式体验
- 保留现有导入、检索、知识综合、选题确认与口播业务流程
- 使用代码生成的颜色、渐变与装饰，不引入参考图的人物、品牌或素材

Acceptance:

- 页面具有一致的圆角卡片、浅色背景、彩色重点区与清晰行动入口
- 桌面与窄屏均可使用
- 用户仍可完成完整 V1 日常操作流程
- UI 不复制 Core 业务逻辑
- 现有 UI 与全量回归测试通过

---

## TASK-021 — Usable AI Answering and Topic Resilience

Status: DONE
Dependencies: TASK-005, TASK-009, TASK-010, TASK-016
Owner: MAIN（跨服务 Provider 接入与验收）

Acceptance record: 2026-09-09 MAIN reproduced the user's two-PDF failure locally. Semantic duplicate Topic Knowledge pages (`ai视频` / `ai 视频`) now resolve deterministically to the most recently updated derived page without changing local data. The UI no longer presents test-only Mock output as a real answer. It selects a configured DeepSeek/OpenAI-compatible chat-completions provider, otherwise returns a structured `provider_not_configured` result with the local evidence chain intact. The adapter uses no vendor SDK, sends only the retrieved local context, and has contract tests for endpoint, headers and request body. MAIN verified the user's local data produces five topic candidates and a non-fabricated answer state; full regression: 65 passed. The existing upstream PyMuPDF/SWIG warning remains tracked under TASK-003.

Scope:

- 处理历史 Knowledge 派生页的语义重复，不能删除或迁移用户本地资料
- 为 UI 配置真实的 OpenAI-compatible Provider，优先支持 DeepSeek
- 未配置密钥时禁止将 Mock 文本伪装为用户可用回答
- 保留 Q&A 的 Knowledge / Notes / Raw 证据链

Acceptance:

- 同主题的空格差异不会阻塞选题生成，且稳定选用最新 Knowledge
- 当前本地两篇 PDF 能生成可解释的选题候选
- 无 Provider 配置时 Q&A 返回证据与明确状态，不产生 Mock answer
- 配置 Provider 后通过 `chat/completions` 生成仅基于本地证据的回答
- 全量测试通过，`.env` 与 `data/` 不纳入 Git

---

## TASK-022 — Session-only AI Provider Configuration UI

Status: DONE
Dependencies: TASK-016, TASK-021
Owner: MAIN（密钥边界与验收）

Acceptance record: 2026-09-10 MAIN added a sidebar configuration form for DeepSeek and OpenAI-compatible endpoints. Provider, model, endpoint and API Key can be applied directly from the UI; the API Key uses a password field and is retained only in the current Streamlit browser session. It is not written to `.env`, logs, data files or Git. MAIN verified the rendered controls on the local Streamlit page and full regression: 67 passed. No live API credential or external request was used during verification.

Scope:

- 在 UI 中填写 Provider、模型、API endpoint 与 API Key
- 将配置仅用于当前浏览器会话的 Semantic Actions
- 提供清除当前会话配置的入口

Acceptance:

- 用户无需编辑 `.env` 即可在 UI 中应用 API 配置
- API Key 使用 password 输入框，且不出现在页面状态、日志、数据或 Git
- 刷新或关闭会话后 Key 自动失效
- 支持 DeepSeek 与 OpenAI-compatible chat-completions endpoint
- 全量测试通过

---

## TASK-023 — UI Contrast and Sidebar Brand Legibility

Status: DONE
Dependencies: TASK-020, TASK-022
Owner: MAIN（小范围 UI 修复与验收）

Acceptance record: 2026-09-10 MAIN raised the contrast of muted page text and sidebar labels, strengthened the sidebar status card, input and button states, and replaced the ambiguous sidebar star with a high-contrast PKB brand mark. A follow-up screenshot exposed that Streamlit's global light form card was still overriding the Provider section while its labels remained light. MAIN added sidebar-specific form, label, submit-button, and expander selectors, then translated the Provider settings labels and validation text to Chinese. A later inspection found the preview server was running an old worktree, so MAIN restarted it from current main. The collapsed-sidebar control is now styled through the live Streamlit header as a deep-purple button with a white icon and outline. MAIN then verified the actual retrieval result expanders: titles, arrows, scores, captions and other muted text now use explicit dark contrast on light cards. MAIN reloaded the local desktop page and ran the full regression suite (67 passed). Main-flow behavior is unchanged; no data, provider settings or credentials were changed.

Scope:

- 修复文字、侧栏控制项与品牌标识的可读性
- 保持现有布局、功能与 session-only API Key 边界

Acceptance:

- 常规文字与辅助文字在浅色页面上清晰可读
- 侧栏输入框、按钮、展开配置区和流程项有明确前景/背景对比
- 品牌标识可辨认，且不引入外部图片资源
- UI 与全量回归测试通过

---

## TASK-024 — Standalone Roadmap Dashboard

Status: DONE
Dependencies: TASK-016
Owner: MAIN

Acceptance record: 2026-09-11 MAIN added an independent local Streamlit dashboard that parses the canonical ROADMAP.md at render time. It shows completion progress, status filters, dependencies, owners and the existing acceptance/progress record for every task. The dashboard does not poll; it reflects a task only after MAIN has accepted it and updated ROADMAP.md, then the page is reloaded. The original knowledge-base page remains unchanged. MAIN verified the standalone light, high-contrast page at 127.0.0.1:8502 and ran the full regression suite (69 passed).

Scope:

- 独立显示 ROADMAP.md 的任务状态和说明
- 不维护第二份任务状态
- 不改动原知识库页面

Acceptance:

- 页面展示总任务、完成进度、可推进和受阻任务
- 每项任务可查看依赖、负责人和最近记录
- 仅在 ROADMAP.md 被 MAIN 更新后、页面重载时同步
- 全量回归测试通过

---

# M7 — Cross-platform Hardening

## TASK-017 — Windows Core Smoke Test

Status: BLOCKED  
Dependencies: TASK-010, TASK-011, TASK-012（M4 core loop stable）
Suggested branch: `chore/windows-compat`

Progress: Core loop dependencies are complete. The task remains BLOCKED because no real Windows 10/11 environment is currently available for install, path, encoding and runtime validation.

Scope:

只验证核心代码：

- install
- PDF
- Idea Card
- Notes
- Index
- Retrieval
- Topics / Script
- paths / encoding

Not required:

- Windows WeChat sync

Acceptance:

- Core 在 Windows 可运行
- 平台差异没有渗进 Core

---

## TASK-019 — Windows WeChat Favorites POC

Status: BACKLOG  
Dependencies: TASK-017

使用 Windows 10/11、已登录的微信 4.x 和三条真实收藏完成独立可行性验证：

```text
微信公众号文章 → ARTICLE → IMPORT
视频 / 视频号 → VIDEO → IGNORE
普通网页 URL → URL → IGNORE
```

Acceptance:

- 公众号文章可取得标题、正文和来源，并转换为现有 UnifiedDocument 后写入 Raw
- 第二次运行不重复导入，微信重启后再次运行仍不重复
- 视频、视频号和普通网页 URL 不进入知识库
- Adapter 故障不影响 PDF、Idea、Notes、Knowledge、Retrieval、Topics 或 Script
- 候选工具和命令必须通过真实源码、版本与本机运行证据验证，不得把搜索结果当作完成方案

不得为它维护一套长期 Windows branch。

---

## TASK-018 — Windows Scheduler Adapter

Status: BACKLOG  
Dependencies: TASK-017, TASK-019 PASS

在 Windows Favorites POC 真实通过后，使用 Windows Task Scheduler 适配定时任务。

---

## TASK-025 — Hybrid Semantic Retrieval

Status: DONE
Dependencies: TASK-008, TASK-010, TASK-020  
Owner: MAIN + TASK-025 Worker  
Suggested branch: `feat/hybrid-semantic-retrieval`

Acceptance record: 2026-09-13 MAIN reviewed the Worker branch and three repair rounds, then integrated the accepted commits into `main`. Retrieval now combines explainable title/tag/keyword/Topic signals with DashScope-compatible embedding cosine similarity while keeping total Related contribution at or below 0.10. The Streamlit UI exposes independent browser-session chat Provider and DashScope Embedding settings; disabling either does not clear the other, no key is written to `.env` or Git, and an explicitly disabled UI semantic client cannot fall back to environment credentials. MAIN verified the merged source and diff, fixed-vector semantic recall with different wording, request/response contract and source evidence, a complete Streamlit form-to-HTTP-to-ranked-result vertical slice against a local compatible endpoint, preserved PDF-import refresh behavior, and merged-main regression (79 passed). The remaining V1 limitation is that each semantic request re-embeds current Index metadata, which adds API latency, cost, and metadata egress; Raw, Notes, and Knowledge bodies are not sent.

Trigger: 2026-09-12 用户真实检索样本显示，仅关键词和 Related 规则无法召回“人物动作更自然”与“运动一致性 / 镜头连续性”等不同措辞的内容。

Scope:

- 在现有本地 JSON Index 上增加可替换的本地语义相似度层
- 保留标题、标签、关键词、Topic 的可解释直接匹配
- 定义各信号权重；Related 总贡献不得超过 0.10
- 输出每个候选的语义分数与来源证据
- 支持离线最小样本与真实 UI 检索验收

Not in scope:

- 云端向量数据库
- 把 Raw / Notes / Knowledge 改造成 Chunk 主架构
- 修改真实 API Key 或迁移已有用户数据

Acceptance:

- `AI视频` 仍优先召回视频文章
- 同义但不同措辞的 AI 视频问题可命中语义相关文章
- Related 链接数量不能主导排名
- 结果仍可追溯到 Index / Note / Raw 来源
- 自动测试、真实 UI 样本、git diff 均由 MAIN 验收

---

# M8 — V2 Multi-user Access

V2 以当前稳定基线 `cd00dd2` 为起点。首期只验证两个受邀测试身份：管理员 A 和普通成员 B。Cloudflare Access 提供 HTTPS／登录入口，Cloudflare Tunnel／`cloudflared` 转发到腾讯云 CVM 上的现有 Python／Streamlit；应用按已校验身份隔离 `data/users/<user_id>/{raw,notes,knowledge,index,history}`。

本里程碑的设计任务必须先于实现任务通过 MAIN 验收。V2 不是把 V1 的共享目录直接搬到云服务器；V1 的本地单用户模式、现有数据和回归能力必须保留。管理员首期只拥有运行维护和自己的知识库权限，不默认读取成员内容或全局历史。

## TASK-027 — V2 Multi-user Architecture and Documentation Alignment

Status: DONE
Dependencies: `cd00dd2`（V1 stable baseline）
Owner: TASK-027 Worker + MAIN review

Scope:

- 对齐 `PRODUCT.md`、`ARCHITECTURE.md`、`TECH_STACK.md` 和 `README.md` 的 V1／V2 边界，并向 MAIN 提交 `ROADMAP.md` 状态建议
- 说明 Cloudflare Access、Tunnel、腾讯云 CVM、应用身份、`admin`／`member` 角色和用户目录隔离
- 明确 Raw、Notes、Knowledge、Index、History、来源、下载和缓存的用户范围
- 记录认证失败、非法角色、路径越权、存储失败、迁移和回滚边界

Not in scope:

- 业务代码、认证适配器、用户存储、UI 登录状态或生产部署
- 真实域名、身份提供商、服务器规格、密钥、API Token 或生产配置
- V1 数据迁移、版本 tag、GitHub 推送和远端写入

Acceptance:

1. 文档明确 V1 单用户本地模式仍可运行，以及保留它的离线、低运维和回滚价值。
2. 文档明确 Access 入口、JWT 身份来源、`admin`／`member` 行为、`data/users/<user_id>/` 目录和 History 隔离。
3. A 与 B 互不可读取、检索、下载或查看对方来源和历史；管理员不因角色自动获得成员数据权限。
4. 无身份、非法 JWT、未知／冲突角色、非法路径和存储故障均失败关闭，不回退到共享目录。
5. 文档没有把认证、云端部署、迁移或 V2 运行能力写成已完成；无真实凭据；五份核心文档约束一致。

Acceptance record: 2026-09-17 09:42 MAIN 检查了五份核心文档 diff、链接、命令、凭据扫描和 V1／V2 一致性；保留 V1 本地单用户模式，确认 Access JWT、角色、用户根目录、历史隔离、失败关闭、迁移与回滚边界均为未实现规划。源码基线由并行 TASK-034 在同一 `cd00dd2` 基线上完成回归，结果为 `98 passed`。TASK-027 PASS。

## TASK-028 — Authentication and Role Minimal Slice

Status: DONE
Dependencies: TASK-027 DONE
Owner: TASK-028 Worker + MAIN review
Suggested branch: `feat/v2-auth`

目标：在应用层通过 Streamlit 公开的 `st.context.headers` 解析 Cloudflare Access 的 `Cf-Access-Jwt-Assertion`，校验签名、issuer、audience、时间和 `sub`，生成明确的 `IdentityContext`，并对无身份、非法身份和未知／冲突角色失败关闭。

Acceptance:

- 测试请求可得到稳定的内部身份和显示信息，用户目录键不直接使用邮箱。
- `admin` 与 `member` 行为可区分；未知身份不能默认变成任何角色。
- 缺少或伪造身份时不会回退到共享 V1 用户。
- 不记录认证头、Cookie、密钥或真实凭据。

Progress: 2026-09-17 09:49 可见 Task `01a0ad0c-4e33-7c42-8ae3-24b12d019510` 已从 `89ab84b` 创建独立 worktree `/Users/mac/.codex/worktrees/476d/personal-ai-kb-spec`，由 GPT-5.6 Luna Max Worker 执行；等待 Completion Report 和 MAIN 验收。

Acceptance record: 2026-09-17 13:30 MAIN 验收 PASS，slice commit `80814a5`，merge commit `9b47739`（`--no-ff` 合入本地 `main`）。检查证据：`pytest` 116 passed（基线 98，新增 18）且仅存 TASK-003 已跟踪的上游 PyMuPDF／SWIG 警告；`uv lock --check` 通过。逐条 Acceptance：①`user_id = "u_" + sha256(issuer + "\0" + sub)` 与 `ARCHITECTURE.md §5.5` 一致，同一 token 重复调用结果相等，测试断言邮箱不出现在目录键中；②`Role`／`is_admin` 可区分，`role_mapping` 无匹配时抛 `unknown_role`，同一 `sub` 命中双角色抛 `conflicting_role`，均失败关闭；③仅读取 `Cf-Access-Jwt-Assertion` 且从不读 Cookie，`auth_enabled=False` 时不触碰 `st.context.headers`，认证失败 `st.error + st.stop()`，认证成功亦 `st.stop()`，在 TASK-029 完成前不进知识库，无共享 V1 回退；④auth 模块内无任何 `logging`／`print`，`IdentityContext` 的 `issuer`／`subject` 设 `repr=False`，`.env.example` 认证项为空，改动扫描无硬编码密钥。MAIN 清单其余项：diff 仅限约定 scope 且无无关重构；仅接受 RS256 且 JWKS 必须为 `issuer + /cdn-cgi/access/certs`、不接受请求自带公钥；无 `/Users` 硬编码与 macOS 专属 API；未触碰 Raw／Notes／Knowledge／Retrieval；新增 `pyjwt[crypto]` 属 `TECH_STACK.md` 授权的认证任务内依赖锁定。非阻塞观察（留待后续）：JWKS 每次认证重新拉取、无缓存，部署时评估；sidebar 身份卡片与 TASK-031 有轻微重叠，TASK-031 仍需补退出／重新登录入口。

## TASK-029 — User-scoped Storage and Retrieval Isolation

Status: DONE
Dependencies: TASK-028 PASS
Suggested branch: `feat/v2-user-storage`

目标：将 Raw、Notes、Knowledge、Index、上传文件、导出文件、检索入口和用户内容型缓存绑定到当前用户根目录，并保留 V1 本地兼容根目录。

Acceptance:

- A 写入的资料在 B 的列表、检索、问答来源和下载入口中不可见，反向同样成立。
- 路径穿越、空用户标识、越权根目录和读写失败均被拒绝，不使用共享目录回退。
- V1 本地单用户路径和 PDF／卡片／检索回归通过。

Acceptance record: 2026-09-17 14:20 MAIN 验收 PASS，slice commit `4d2446e`，merge commit `3d216f9`（`--no-ff` 合入本地 `main`）。检查证据：`pytest` 124 passed（基线 116，新增 8）且仅存 TASK-003 已跟踪的上游 PyMuPDF／SWIG 警告；V1 本地路径回归通过。逐条 Acceptance：①`test_user_data_is_not_visible_to_other_user` 验证 Alice 与 Bob 的 idea card 互相不可检索，各用户 index 独立；②`validate_user_id` 拒绝空值、邮箱、`..`、长度非法等恶意标识，`resolve_user_root` 二次校验路径解析后仍位于 `data/users/` 下，`prepare_user_root` 失败时抛出可读错误；③`test_uipaths_v1_root_without_user_id` 与全量回归验证 V1 本地单用户路径不变。实现要点：`UIPaths` 根据 `user_id` 切换 `<data_dir>/users/<user_id>/` 或 V1 根目录；`UIService` 接受可选 `identity`，认证通过时自动准备用户隔离布局；`app.py` 认证成功后不再 `st.stop()`，而是将 identity 注入服务；核心存储／检索／问答服务内部无改动，仅通过目录参数实现隔离；`tests/conftest.py` 新增 `tmp_path` fixture 覆盖，把 pytest 临时目录限定在项目 `tests/_tmp/` 内，避免沙箱拦截系统 temp。

## TASK-030 — User-scoped History and Audit Records

Status: DONE
Dependencies: TASK-029 PASS
Suggested branch: `feat/v2-history`

目标：按用户保存问答、选题和口播历史，并记录必要的操作时间与结果状态；历史不能被其他用户读取或静默覆盖。

决策：V2 首期管理员不能查看成员全局历史。若未来需要审计成员内容，必须另立明确授权、只读范围和验收任务。

Acceptance record: 2026-09-17 17:05 MAIN 验收 PASS，slice commit `2cb65da`，merge commit `57fa873`（`--no-ff` 合入本地 `main`）。检查证据：`pytest` 129 passed（基线 124，新增 5）且仅存 TASK-003 已跟踪的上游 PyMuPDF／SWIG 警告；`uv lock --check` 通过。实现要点：新增 `pkb.history` 的 `HistoryRecord`／`HistoryStore`，每条历史记录独立 JSON 文件并以独占 `x` 模式写入，重复 ID 明确拒绝覆盖；记录仅保存 kind、UTC 时间、结果状态和问答／选题／口播必要标签，不复制完整答案、口播正文、来源或 Provider 内容；`UIService` 在 `answer`／`generate_topics`／`write_script` 成功后追加对应记录，并暴露 `list_history()`。逐项验证：①`test_history_store_appends_without_overwrite` 验证拒绝覆盖；②`test_history_store_returns_chronological_order` 与 `test_history_store_rejects_corrupt_record` 验证按时间读取、损坏记录不静默忽略；③`test_history_is_scoped_to_each_user` 验证 Alice 与 Bob 的问答／选题历史互不可见；④`test_script_result_is_recorded_after_generation` 验证口播生成后记录状态、主题和标题。管理员未获得任何全局历史读取路径。

## TASK-031 — UI Login State and Role Hint

Status: DONE
Dependencies: TASK-028 PASS
Suggested branch: `feat/v2-ui-identity`

目标：在现有 Streamlit UI 显示当前登录身份、角色、重新登录／退出入口和可读错误，不显示完整认证头、密钥或服务器路径。

Acceptance record: 2026-09-17 17:26 MAIN 验收 PASS，slice commit `10e17ae`，merge commit `d1af2b5`（`--no-ff` 合入本地 `main`）。检查证据：`pytest` 132 passed（基线 129，新增 3）且仅存 TASK-003 已跟踪的上游 PyMuPDF／SWIG 警告；`uv lock --check` 通过。实现要点：侧边栏 V2 身份卡只显示安全显示名与角色，当 `display_name` 回退为邮箱时统一显示「已认证用户」，不渲染 `user_id`／`subject`／`issuer`／邮箱或用户目录绝对路径；新增 Cloudflare Access 官方退出路径 `/cdn-cgi/access/logout`，以浏览器相对路径解析当前 origin，避免硬编码生产域名或内部服务器路径；V2 提示改为「数据按当前登录身份隔离」，移除 TASK-029／TASK-030 完成前的过时说明。逐项验证：①`test_v2_identity_status_uses_safe_fields_and_official_logout_path` 验证身份、角色、认证状态与退出链接；②`test_identity_display_name_never_echoes_email_fallback` 验证邮箱回退不泄露邮箱；③`test_v2_sidebar_reports_scoped_storage_without_stale_pending_copy` 验证旧文案和敏感服务器路径不出现。认证失败路径沿用 TASK-028 的 `st.error + st.stop()`，本任务不修改认证适配器逻辑。

## TASK-032 — Cloudflare Access／Tunnel and Tencent Cloud Deployment

Status: BLOCKED
Dependencies: TASK-031 PASS
Suggested branch: `feat/v2-cloud-deploy`

目标：提供可复用的部署配置和操作文档，在测试域名完成健康检查与双身份验证。CVM 上的 Streamlit 仅监听本机，`cloudflared` 使用出站 Tunnel；持久化目录、重启恢复和源站不可绕过必须有证据。

限制：生产部署、DNS 修改、身份提供商配置、远端密钥写入和服务器权限变更必须由 MAIN 另行确认，不在前置文档任务中预授权。

## TASK-033 — Dual-identity End-to-end and Security Regression

Status: BLOCKED
Dependencies: TASK-030 PASS、TASK-032 PASS
Suggested branch: `test/v2-e2e-security`

目标：以 A／B 执行导入、检索、问答、口播、历史和下载全流程，验证隔离、失败路径和 V1 回归，并形成发布前验收记录。

Acceptance:

- 两个身份通过同一 Access 入口到达应用并显示正确身份／角色。
- A／B 的内容、来源、检索候选、下载和历史互不可见。
- 无身份、非法 JWT、越权路径、角色错误、Tunnel／服务不可用和磁盘失败均有确定错误。
- V1 既有测试与本地单用户最小闭环通过；无密钥、真实私人资料或未授权远端写入。

## TASK-035 — Local Account Multi-user Mode

Status: DONE
Dependencies: TASK-030 PASS、TASK-031 PASS
Suggested branch: `feat/v2-local-auth`

目标：在不购买域名、不使用 Cloudflare Access 的前提下，用本机账号密码完成双用户数据隔离，为低风险朋友间分享提供实验入口。

Acceptance:

- `PKB_AUTH_MODE=local` 时先显示登录页，认证成功后进入独立用户根目录。
- 用户名密码只以 PBKDF2 哈希保存在 `config/local_users.json`，不写明文或日志。
- A／B 映射到不同的 `data/users/<user_id>/`，无法看到对方 PDF、笔记、索引和历史。
- V1 默认 `PKB_AUTH_ENABLED=false` 不改变；Cloudflare Access 模式保留。
- CLI 能安全生成哈希并添加本地用户；全量测试通过。

Acceptance record: 2026-09-17 18:26 MAIN 验收 PASS，feature branch `feat/v2-local-auth`，slice commit `c02dfbc`，集成切片 commit `2ef92ca`。检查证据：`pytest` 145 passed（基线 132，新增 13）且仅存已知 PyMuPDF／SWIG 5 条上游警告；`uv lock --check` 通过。实现要点：新增 `src/pkb/auth/local.py`，使用 `pbkdf2_sha256`、随机 salt 与 `hmac.compare_digest`；本地用户名派生 `u_ + sha256("local\0username")`，直接复用既有 `UserScopedStorage`，未新增数据目录或迁移；UI 本地模式登录后只在会话状态保存 `IdentityContext`，退出时清除会话；CLI 新增 `auth-hash-password` 与 `auth-add-local-user`，本地用户文件原子写入并设 600 权限；文档同步说明该模式不替代 Cloudflare Access 生产入口。后置修复 commit `aba1ba4`：允许先复制空模板 `config/local_users.example.json`，再由 CLI 添加用户；全量测试仍为 145 passed。

---

# M9 — GitHub Presentation

## TASK-034 — GitHub Project Introduction and Demo Assets

Status: DONE
Dependencies: 无；与 TASK-027 并行执行
Owner: MAIN + TASK-034 Worker

目标：重写 README，突出真实产品价值、V1 闭环、当前边界、V2 路线、运行方式和黑客松演示路径；加入不含敏感数据的架构／数据流图或现有 UI 截图。

允许修改：`README.md`、`docs/assets/` 下的展示素材及其引用；不得修改业务代码、密钥、ROADMAP 状态或推送远端。

Acceptance:

- 新用户能在 3 分钟内理解产品解决的问题、运行方式和演示步骤。
- 所有命令与当前代码一致；图片在 GitHub 相对路径可渲染。
- 不包含真实 API Key、个人数据或未实现功能的虚假承诺。

Acceptance record: 2026-09-17 09:42 MAIN 检查 README 产品价值、V1 完整闭环、输入限制、演示路径、CLI 命令、Provider 与安全边界；SVG XML、相对引用、敏感信息扫描和本地渲染检查通过。Worker 在同一基线完成 `98 passed`、CLI help／health 和 Streamlit 入口导入验证。未执行远端推送或 GitHub 页面发布。TASK-034 PASS。

---

# 4. 当前调度策略

当前可以推进：

- TASK-017 Windows Core Smoke Test：仅在真实 Windows 10/11 环境可用后派发

必须串行：

- TASK-017 PASS → TASK-019 Windows WeChat Favorites POC
- TASK-019 PASS → TASK-018 Windows Scheduler Adapter
- TASK-027 DONE → TASK-028 → TASK-029 → TASK-030 DONE
- TASK-028 PASS → TASK-031 DONE
- TASK-029、TASK-031 PASS → TASK-032
- TASK-030、TASK-032 PASS → TASK-033

V2 正式部署调度仍暂停：TASK-032 涉及真实域名、DNS、身份提供商配置、腾讯云 CVM 权限变更、远端密钥写入和生产部署，须由 MAIN 另行取得主人确认后再派发；TASK-033 仍依赖 TASK-032 PASS，继续 BLOCKED。

本地无域名分享线已完成 TASK-035，可作为朋友间低敏感试用入口；它不替代 TASK-032／TASK-033 的正式 Access 部署与双身份 E2E 验收。

继续阻塞：

- TASK-013 当前安全边界下不再重复派发
- TASK-014 / TASK-015 等待 TASK-013 真实 PASS

Manual WeChat Article Import 是 V1 主线；Favorites 自动同步 POC 不阻塞核心知识库。

TASK-026 Manual WeChat Article Import、TASK-027 V2 文档对齐和 TASK-034 GitHub 展示均已完成，不再作为“可派发”任务重复列入。V2 认证、存储、历史和部署任务不能绕过已记录的依赖顺序。

---

# 5. Worker Completion Contract

每个 Worker 完成时必须回报：

```text
TASK:
STATUS: PASS / BLOCKED

完成：
- ...

修改文件：
- ...

测试：
- ...
- X passed / X failed

未解决：
- ...

Branch:
Worktree:

Commit:
（如尚未获准 commit，写 NOT COMMITTED）

验收步骤：
1.
2.
3.

风险 / 说明：
- ...
```

MAIN 不接受“已完成”作为唯一验收证据。

---

# 6. MAIN 验收规则

MAIN 需要检查：

- Task 是否只做约定 scope
- Diff 是否合理
- Tests 是否通过
- Acceptance 是否全部满足
- 是否引入无关重构
- 是否破坏跨平台要求
- 是否碰了 Raw immutable 原则

PASS：

- 才允许进入 merge / DONE
- 更新 ROADMAP
- 解锁下一依赖任务

FAIL：

- 返回原 Worker
- 保持原 worktree
- 只修失败项
- 增加对应 regression test
- 再次提交 REVIEW
