# TASK-040 Clickable Q&A Sources and PDF Preview

## Goal

Keep parenthesized citations in Q&A answers while making each citation open the exact original source: public-account URLs in a new tab and local PDF originals in an in-app preview.

## Background

TASK-038 added per-answer citation IDs and invalid-reference marking. The source-chain cards already have a safe HTTP(S) URL action and a PDF download button, but answer citations themselves are plain text. The current UI's configured per-user `raw_dir` and `_source_raw_path` resolver must remain the source boundary.

## Dependencies

- TASK-038 — Q&A citation labels (already implemented in the MAIN working tree).
- This task is independent from TASK-039 and must use its own feature branch and worktree.

## Scope

- Change only Q&A answer rendering/source navigation and focused UI tests.
- Keep `(来源 N)` appearance and map each displayed citation ID to exactly one `QASource`.
- Clicking a public-account citation opens its validated HTTP(S) original in a new browser tab.
- Clicking a PDF citation opens an in-app preview of the immutable original PDF, using already installed PyMuPDF; do not add a package.
- Resolve PDFs only through the current request's `raw_dir` and a validated document ID. Missing originals should show a clear unavailable state.
- Preserve source cards and their existing access actions for users who do not click inline citations.

## Forbidden

- Do not change retrieval scoring, Notes, Knowledge, Raw contents, authentication, invite policy, user-directory resolution, network routes, or dependencies.
- Do not expose arbitrary filesystem paths or serve files outside the current user's `raw_dir`.
- Do not write PDF data to logs, Git, `.env`, or persistent project files.
- Do not read or upload real PDFs or public-account source data; use synthetic UI samples for automated tests.
- Do not alter TASK-038 citation-number assignment or invalid-reference policy.

## Acceptance

- A citation with a WeChat HTTP(S) reference opens exactly that original URL in a new tab.
- A citation for a PDF opens a preview of its original PDF in the knowledge-base UI; it does not merely download the file.
- Invalid citation IDs, unsupported schemes, missing PDFs, and path-traversal IDs never open unrelated content.
- Existing Q&A and UI tests pass; AppTest or an equivalent focused check verifies both source types and the unavailable-PDF path.
- No private data leaves the application and no new dependency is added.

## Completion report

### Text-source follow-up

2026-10-09 21:26：补齐直接粘贴文本来源的正文引用链接，复用当前用户的安全 Raw 定位与预览路由，按文件类型展示 PDF 或原始纯文本。改动限定于 UI、测试及说明文档；不修改用户资料、认证、检索或依赖。全量 227 项通过，包括纯文本精确保留、跨用户／路径穿越／符号链接拒绝与原有 PDF 预览。主人当前回答实际点击“来源 1”打开对应原文；启动器重启后复验成功。主工作区 main，提交前 HEAD `316d071`；最终修复提交见本文件的 Git 历史。本地截图：`output/TASK-040-text-source-preview.jpg`。

Return TASK, STATUS, changes, modified files, tests and outcomes, unresolved issues, risks, branch, worktree, commit, and acceptance steps. Commit on the assigned task branch before requesting MAIN review.
