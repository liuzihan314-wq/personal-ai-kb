# 微信收藏输入路线交接文档

> 项目：Personal AI Knowledge Base  
> 用途：交接给 Codex MAIN / Coordinator  
> 状态基线：2026-09-15  
> 目标：重新冻结微信收藏输入需求、macOS/Windows 平台路线与 V1 兜底方案

---

## 1. 本次需要 MAIN 接受的核心结论

### 1.1 TASK-013 仍保持 `BLOCKED`

当前任务：

- `TASK-013｜macOS WeChat Favorites Feasibility POC`
- Branch：`poc/task-013-wechat-macos`
- Commit：`b4369b052914c036cc856d49f9bad54a756d022b`

当前结论不是“macOS 微信同步基本完成”，也不是“macOS 永久不可实现”。

准确结论是：

> 在当前安全边界与授权范围内，macOS 微信 4.1.13 的真实 Favorites 自动同步闭环仍被阻塞。

已经确认：

- 微信版本与数据目录已定位；
- `favorite.db` / `favorite_fts.db` 会随收藏行为发生变化；
- 数据库不是普通 SQLite；
- 安全探针和 synthetic metadata 白名单过滤测试通过。

尚未完成：

- 无法确认真实新增公众号文章记录；
- 无法读取真实收藏内容类型 / 公众号标记；
- 无法取得真实标题、正文、来源；
- 无法获得稳定 item ID；
- 无真实去重证据；
- 无真实视频 / 视频号过滤证据；
- 无真实普通 URL 过滤证据；
- 微信重启后仍无法执行真实同步闭环。

因此：

- 不进入 TASK-014 生产化；
- 不将 synthetic test 通过误写为真实微信同步通过；
- 不在当前主力 Mac 上直接关闭 SIP、扫描进程 SQLCipher key、附加微信进程或扩大到高权限内存解密路线；
- 保留 TASK-013 代码、日志、测试与失败证据，作为未来重新评估依据。

---

## 2. 产品需求与自动化能力必须拆开

V1 的真实产品需求是：

> 用户指定的微信公众号文章能够可靠进入知识库，并进入既有 Raw → Notes → Knowledge / Index → Retrieval 流程。

“自动从微信收藏夹发现新增文章”是输入效率增强，不应继续作为整个 V1 的阻塞条件。

因此微信输入拆成两个独立 Adapter：

### A. Manual WeChat Article Adapter — V1 MUST HAVE

用户主动导入公众号文章。

推荐 V1 最小能力：

1. 用户在 Web UI / CLI 中提供公众号文章 URL；
2. 仅接受确认属于微信公众号文章的输入；
3. 自动提取正文成功时，生成现有 `Unified Document`；
4. 自动提取失败时，允许用户粘贴：
   - 标题
   - 正文
   - 原始公众号 URL
5. 写入 Raw；
6. 后续进入现有 Notes / Knowledge / Retrieval 流程。

该入口是长期可靠兜底，不依赖微信收藏内部数据库。

### B. WeChat Favorites Auto Sync — Experimental / POC

目标仍保留：

```text
微信收藏新增
→ 自动检测新增
→ 只允许微信公众号文章
→ 排除视频 / 视频号 / 普通 URL
→ 获取标题 / 正文 / 来源
→ 去重
→ Raw
```

但是：

> 自动收藏同步失败 ≠ V1 失败。

只有真实平台 POC 验证通过后，才允许进入生产化。

---

## 3. 微信内容过滤规则保持不变

### Favorites 自动同步

只允许：

- 微信公众号文章

必须忽略：

- 视频
- 视频号
- 普通网页 URL
- 普通链接
- 图片
- 音频
- 文件
- 小程序
- 聊天记录
- 其他非公众号收藏内容

要求继续采用 allow-list，而不是“非视频即导入”的 block-list。

### Manual WeChat Article Import

允许用户主动导入：

- 明确的微信公众号文章 URL
- 或公众号文章正文 + 原始 URL

普通网页 URL 不应因为“手动输入”而自动变成公众号知识来源。

---

## 4. Windows 路线重新定义

Windows 不是已完成方案，只是备用 POC 路线。

当前 ROADMAP：

### TASK-017｜Windows Core Smoke Test

状态：`BLOCKED`

目标：

- 证明 Core 在 Windows 10/11 上可运行；
- 验证 PDF、Idea Card、Notes、Index、Retrieval、Topics、Script；
- 验证路径与编码；
- 不包含微信同步。

当前阻塞：

- 缺少可用于真实验证的 Windows 10/11 环境。

### TASK-019｜Windows WeChat Adapter

状态：`BACKLOG`

依赖：

- TASK-017

目标：

- 独立验证 Windows 微信 Favorites 输入；
- 不允许将 Windows 平台差异侵入 Core；
- 不维护长期 `windows` Git 分支。

当前没有证据证明 Windows 已经能够稳定完成：

```text
Favorites 枚举
→ 公众号文章识别
→ 视频 / 普通 URL 排除
→ 正文提取
→ 增量同步
→ 重启后稳定去重
```

因此文档和代码注释中不得将 Windows 描述为“已解决方案”。

---

## 5. Windows 任务优先级建议

实际推进顺序建议调整为：

```text
TASK-017 Windows Core Smoke Test
        ↓ PASS
TASK-019 Windows WeChat Favorites POC
        ↓ PASS
TASK-018 Windows Scheduler Adapter
```

理由：

- Scheduler 只是“什么时候执行”；
- 当前首先要证明“有什么可执行的 Windows 微信同步能力”；
- 在 TASK-019 通过之前，不应优先投入 Windows Scheduler。

---

## 6. TASK-019 的最小真实闭环

Windows POC 不要一开始做完整同步产品。

准备至少三条真实收藏：

- A：微信公众号文章 × 1
- B：视频 / 视频号 × 1
- C：普通网页 URL × 1

最低验收：

```text
A → ARTICLE → IMPORT
B → VIDEO → IGNORE
C → URL → IGNORE
```

并验证：

1. A 能取得标题、正文和来源；
2. A 能转换为现有 Unified Document；
3. A 成功写入 Raw；
4. 第二次运行不重复导入；
5. 微信重启后再次运行仍不重复；
6. B / C 不进入知识库；
7. 微信 Adapter 故障不影响 PDF / Idea Card / Notes / Knowledge / Retrieval / Topics / Script。

只有该最小闭环真实通过，Windows Favorites 才可从 POC 进入生产化讨论。

---

## 7. 架构保持不变

核心数据流保持：

```text
Input Adapter
→ Unified Document
→ Raw
→ Notes
→ Related / Index
→ Knowledge
→ Retrieval
→ Topics
→ Script
```

微信输入只是 Adapter。

建议结构：

```text
WeChat Input
├── Manual Article Adapter        # V1 稳定入口
└── Favorites Auto Sync Adapter   # POC / Experimental
    ├── macOS                     # TASK-013 BLOCKED
    └── Windows                   # TASK-019 BACKLOG / 未验证
```

不得因为平台 POC 失败而修改 Raw / Notes / Knowledge / Retrieval 等核心层。

---

## 8. 建议修改的项目文档

### PRODUCT.md

需要修改：

- 将“微信收藏自动同步”从 V1 hard requirement 降为 experimental / 非阻塞能力；
- 新增“Manual WeChat Article Import”为 V1 MUST HAVE；
- 明确 V1 成功不依赖 Favorites 自动同步。

### ARCHITECTURE.md

需要修改：

- WeChat 输入拆分为：
  - Manual WeChat Article Adapter
  - Favorites Auto Sync Adapter
- macOS / Windows 只是 Favorites Adapter 的平台实现。

### TECH_STACK.md

需要修改：

- macOS Favorites：`BLOCKED POC`
- Windows Favorites：`POC CANDIDATE / NOT VERIFIED`
- 不把 Windows 写成已验证路线。

### ROADMAP.md

建议：

- 新增 `TASK-0XX｜Manual WeChat Article Import Adapter`
- TASK-013 保持 `BLOCKED`
- TASK-017 → TASK-019 → TASK-018 作为 Windows 实际推进顺序
- 自动同步不再阻塞 V1 主闭环。

### CODEX_HANDOFF.md

可做小改：

- Worker 不得把 Windows 方案描述成已完成；
- 平台 POC 失败不得扩散到 Core；
- Favorites 自动同步任务必须基于真实样本验收。

---

## 9. MAIN 当前应执行的动作

请按顺序执行：

1. 阅读当前 `PRODUCT.md`、`ARCHITECTURE.md`、`TECH_STACK.md`、`ROADMAP.md`、`CODEX_HANDOFF.md`。
2. 对照本交接文档，列出与现有文档的差异。
3. 确认 TASK-013 继续保持 `BLOCKED`，不要进入生产化。
4. 不把 Windows 描述为已完成方案。
5. 提议一个新的 `Manual WeChat Article Import Adapter` Task ID、依赖与 Acceptance Criteria。
6. 调整 Windows 路线的实际优先级为 `TASK-017 → TASK-019 → TASK-018`。
7. 给出需要修改的 5 份项目文档的最小 diff 计划。
8. 暂时不要实现 Windows POC。
9. 暂时不要扩大 macOS POC 权限边界。
10. 先等待用户确认文档与 ROADMAP 调整，再编码。

---

## 10. Manual WeChat Article Adapter 建议验收标准

建议 MAIN 为新 Task 至少定义：

1. 能接受一个微信公众号文章 URL；
2. 能明确拒绝普通网页 URL；
3. 成功抓取时生成符合现有 Unified Document Schema 的对象；
4. 保存 Raw；
5. Raw 不被 AI 覆盖；
6. 同一文章重复导入不重复写入；
7. 自动抓取失败时可通过“标题 + 正文 + 原始 URL”手工提交；
8. 手动导入失败不能影响其他输入 Adapter；
9. 不修改 Notes / Knowledge / Retrieval 的核心接口；
10. 有真实公众号文章样本的最小端到端验收。

---

# 给 MAIN 的启动提示词

请先完整阅读 `WECHAT_INPUT_ROUTE_HANDOFF.md`，并结合当前项目根目录中的：

- PRODUCT.md
- ARCHITECTURE.md
- TECH_STACK.md
- ROADMAP.md
- CODEX_HANDOFF.md

完成一次“微信输入路线重新对齐”。

本轮先不要编码，不要创建 Windows 微信实现，也不要扩大 macOS POC 的权限边界。

请输出：

A. 你对 TASK-013 为什么仍然是 BLOCKED 的理解  
B. 为什么 Windows 目前只能定义为备用 POC，而不是完成方案  
C. 为什么 V1 应加入 Manual WeChat Article Adapter  
D. V1 微信输入新的 MUST HAVE / EXPERIMENTAL 边界  
E. 建议新增的 Manual WeChat Article Task ID、Dependencies、Scope、Acceptance Criteria  
F. TASK-017 / TASK-019 / TASK-018 的推荐执行顺序与理由  
G. PRODUCT / ARCHITECTURE / TECH_STACK / ROADMAP / CODEX_HANDOFF 的最小修改清单  
H. 哪些内容当前明确不应该执行

最后等待用户确认。

不要因为本交接文档而自动修改文件；先给出变更计划和 ROADMAP 调整建议。
