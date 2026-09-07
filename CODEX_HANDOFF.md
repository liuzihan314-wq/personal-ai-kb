# Personal AI Knowledge Base — CODEX_HANDOFF.md

> Purpose: 让 Codex 在同一个 Project 下，以 MAIN Coordinator + 多个 Task Worker 的方式安全推进本项目。  
> This file is an operating contract, not a product requirement file.

# 1. First Rule — Do Not Code Immediately

进入这个 Codex Project 后，第一步不是写代码。

必须先读取：

1. `PRODUCT.md`
2. `ARCHITECTURE.md`
3. `TECH_STACK.md`
4. `ROADMAP.md`
5. `CODEX_HANDOFF.md`

然后只输出：

- 你理解的产品一句话定义
- V1 输入
- V1 输出
- V1 明确不做什么
- Raw / Notes / Knowledge / Index 的区别
- macOS / Windows 的平台要求
- V1 为什么不上向量库
- 当前最大技术风险
- ROADMAP 中第一个 READY Task

最后等待用户确认。

**用户确认前，不要开始编码。**

---

# 2. Codex Project / Thread Model

所有任务线程必须属于：

**同一个 Codex Project**

推荐侧边栏结构：

```text
Personal AI Knowledge Base
│
├── MAIN｜Coordinator
├── TASK-001｜Git & Repo
├── TASK-002｜Project Foundation
├── TASK-003｜PDF Import
├── TASK-004｜Idea Card
├── TASK-005｜AI Provider
├── TASK-006｜AI Notes
├── ...
└── TASK-013｜WeChat macOS POC
```

不要为每个 Task 建一个独立 Codex Project。

---

# 3. MAIN Coordinator Role

MAIN 负责：

1. 阅读和维护 ROADMAP
2. 判断任务依赖
3. 判断哪些任务可以并行
4. 给 Worker 发清晰 Task scope
5. 验收 Worker 结果
6. 决定 PASS / FAIL
7. 决定何时 merge
8. 更新 ROADMAP 状态
9. 决定下一批 READY Tasks

MAIN 不应默认亲自实现所有功能。

---

# 4. ROADMAP Ownership

`ROADMAP.md` 只允许 MAIN 更新：

- task status
- dependencies
- owner
- milestone
- acceptance changes

Worker：

- 可以读取 ROADMAP
- 不得自行把 Task 改为 DONE
- 不得自行修改依赖
- 不得自行给自己新增任务

Worker 完成后发 Completion Report，由 MAIN 验收后更新 ROADMAP。

---

# 5. Worker Role

每个 Worker 只做一个明确 Task。

Task prompt 至少包含：

- Task ID
- 目标
- dependencies
- allowed scope
- forbidden scope
- files / directories 可以修改的范围
- acceptance criteria
- expected tests

Worker 不要因为“顺手”而重构无关模块。

---

# 6. Parallelism

只有真正互不依赖、文件边界清晰的任务才并行。

示例：

TASK-003 PDF Import  
与  
TASK-004 Idea Card

可并行。

但：

Topic Generator 依赖 Retrieval / Knowledge，不应提前乱做。

---

# 7. Branch + Worktree

并行 Worker 需要修改同一 repo 时：

- 每个 Worker 使用独立 feature branch
- 每个 Worker 使用独立 worktree
- 不共享同一个可写工作目录

示例：

```text
main

feat/pdf-ingest
  ↳ worktree A

feat/idea-card
  ↳ worktree B

poc/wechat-macos
  ↳ worktree C
```

Worktree 是 Git 隔离工作目录，不是 Agent 本身。

---

# 8. Branch Strategy

长期分支：

- `main`

短期功能分支：

- `feat/...`
- `fix/...`
- `poc/...`
- `chore/...`

不要维护长期：

- `mac`
- `windows`

分支。

macOS / Windows 差异必须通过 Adapter / platform module 管理。

---

# 9. macOS + Windows Contract

## macOS

- 当前主要开发环境
- 当前主要运行环境
- WeChat 自动同步先做 macOS POC
- Scheduler 使用 launchd

## Windows

- 保留为备用运行环境
- Core 尽量跨平台
- 后续做 Core smoke test
- Windows Scheduler / WeChat 属独立 Adapter
- Windows 不阻塞 Mac V1 主线

Worker 写 Core 时：

- 使用 `pathlib`
- 避免写死 `/Users/...`
- 避免无必要 shell-only / macOS-only 代码
- 统一 UTF-8
- 平台逻辑放 Adapter

---

# 10. WeChat Contract

微信收藏输入只允许：

**微信公众号文章**

明确排除：

- 视频
- 视频号
- 普通 URL
- 图片
- 音频
- 小程序
- 文件
- 聊天记录
- 其他收藏

不要因为“都是 link 类型”就全部导入。

WeChat Adapter 必须有白名单识别。

WeChat POC 是高风险外围任务。

POC 失败不能阻塞核心知识库。

---

# 11. PDF Contract

V1 只支持文本 PDF。

不要实现：

- OCR
- 扫描 PDF
- 图片 PDF 识别

如果输入扫描 PDF，应明确返回“不支持”，不要偷偷引入 OCR 依赖。

---

# 12. Knowledge Architecture Contract

必须保持：

```text
Raw
↓
Notes
↓
Knowledge
↓
Index / Retrieval
```

Raw：

- 原始事实
- Immutable

Notes：

- 单篇 AI 理解

Knowledge：

- 多篇编译的当前主题认知

Index：

- 帮程序与 AI 快速定位

所有 AI 结论尽可能可追溯到 Raw。

---

# 13. Retrieval Contract

V1 不引入向量库作为默认方案。

先使用：

- title
- tags
- keywords
- topic
- related
- index
- AI candidate judgment

如果真实测试证明召回不足：

先提交证据和失败案例给 MAIN。

未经确认，不得自行加入 Chroma / Qdrant / Pinecone / Weaviate / Faiss 等架构。

---

# 14. AI Provider Contract

Core 不绑定某一个模型。

Provider 必须：

- 可替换
- 可 mock
- API key 不写进代码
- model / endpoint 走 config

开发阶段 Codex 是工程协作者。

无人值守 AI 能力使用独立 API Provider。

---

# 15. GitHub Contract

用户已有 GitHub 账号，但可能尚未创建 Private Repository。

首次 repo task：

1. 检查本地是否已经是 Git repo
2. 如果没有，初始化
3. 检查 `.gitignore`
4. 确认私人数据不会被跟踪
5. 协助创建 GitHub Private Repo
6. 设置 remote
7. 再 push

GitHub 只保存：

- code
- tests
- docs
- templates

不要上传：

- API keys
- `.env`
- 私人 PDF
- 微信收藏原文
- 真实 Raw / Notes / Knowledge

---

# 16. Git Learning Rule

用户是 Git 初学者，希望在真实项目中学习。

Codex 可以帮助执行和解释 Git，但以下操作属于“改变项目状态 / 历史”的关键操作：

- commit
- merge
- branch deletion
- reset
- rebase
- force push

执行前：

1. 说明准备做什么
2. 说明影响
3. 让用户确认

优先让用户亲自理解这些基本命令：

```bash
git status
git diff
git add
git commit
git push
git branch
git switch
git merge
```

不要在用户不知情的情况下重写历史。

---

# 17. Worker Completion Contract

Worker 完成必须按此格式回报 MAIN：

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
（未获准则 NOT COMMITTED）

验收步骤：
1.
2.
3.

风险 / 说明：
- ...
```

不要只说：

“完成了。”

---

# 18. Review Loop

```text
Worker implements
↓
Worker tests
↓
Completion Report
↓
MAIN reviews diff + tests + acceptance
↓
PASS?
├─ YES → user approves Git action → merge → ROADMAP DONE
└─ NO  → return to same Worker/worktree → fix → regression test → re-review
```

原 Worker 失败后继续在原 worktree 修复，不要另开一个 Agent 重新猜。

---

# 19. MAIN Autonomous Review and Integration

MAIN 收到 Completion Report 后必须自行检查 Task Brief、Acceptance Criteria、修改范围、git diff、测试结果、产品/架构/技术栈约束与禁止项。

- PASS：直接完成正常的短期 branch 提交、fast-forward merge、ROADMAP 更新和依赖解锁，并继续派发已满足依赖且范围不冲突的任务。
- FAIL：向原来的同一个 Task Thread 发送明确的返工要求；Worker 留在原 branch / worktree，只修复失败项，随后由 MAIN 再验收。
- 不得把正常验收、返工、提交、合并或后续派发拆成逐步向用户申请批准的流程。
- MAIN 为每个 Active Task 记录 thread/clientThreadId、branch 与 worktree。Completion Report 未到达或平台只返回 clientThreadId 时，MAIN 仍须定期检查该 worktree 的分支、git status、最新 commit 与可见 Task 状态；发现实现变化即执行同一套验收流程。缺少可见正式线程要如实报告为平台限制，但不能阻塞对已有工作树结果的验收与后续调度。

只有以下情况 MAIN 才暂停请求用户决定：关键需求或架构歧义、明显超出既定范围、高风险或不可逆操作、新增外部账号/权限/付费、数据迁移、连续失败须改变技术路线，或多个重要业务方案需要用户拍板。

`reset`、`rebase`、`force push`、删除分支、改写 Git 历史、公开发布以及敏感配置仍须用户明确确认。WeChat POC 必须保持在既定只读、最小数据范围内；一旦需要超出该范围的方案，交由 MAIN 决定是否请求用户。

---

# 20. First Prompt for MAIN

将以下内容作为 MAIN 的第一条工作指令：

> 请先完整阅读项目根目录中的 PRODUCT.md、ARCHITECTURE.md、TECH_STACK.md、ROADMAP.md、CODEX_HANDOFF.md。  
> 暂时不要写代码，也不要修改任何文件。  
> 请用你自己的话复述：  
> 1）产品解决什么问题；  
> 2）V1 输入与输出；  
> 3）V1 明确不做什么；  
> 4）Raw、Notes、Knowledge、Index 的区别；  
> 5）macOS 与 Windows 的要求；  
> 6）V1 为什么不默认使用向量数据库；  
> 7）当前最大的 3 个风险；  
> 8）ROADMAP 中第一个可执行任务是什么。  
> 最后等待我确认你的理解，再开始下一步。
