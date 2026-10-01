# TASK-039 Search Ranking for Site Deployment Queries

## Goal

Improve local retrieval for mixed Chinese/English queries such as `AI部署网页`, so specific site-building and deployment material is ranked ahead of generic AI material. The real acceptance sample is the owner-provided public-account article titled `用Codex的站点模式做数据分析网站，再通过WorkBuddy发布和分享给朋友`.

## Background

The article is present in the local index and was used by Q&A, but a read-only CLI search ranked it 16th (0.07) for `AI部署网页`; `12.AI 学习之路 · 实战篇之「个人站点系列：网页到底是个啥」` ranked first (0.233). Generic `AI` and broad `网页` overlap currently outweigh deployment-specific relevance.

## Dependencies

- TASK-038 — Q&A citation labels (already implemented in the MAIN working tree).
- This task is independent from TASK-040 and must use its own feature branch and worktree.

## Scope

- Inspect and change only local retrieval query analysis/scoring and its focused tests.
- Use corpus statistics and a small, explicit website/deployment vocabulary map if needed; keep ranking deterministic and explainable.
- Preserve optional embedding behavior and keep Related evidence bounded.
- Add synthetic regression cases that distinguish high-frequency generic matches from specific deployment/site matches.

## Forbidden

- Do not edit UI, Q&A citation rendering, Notes, Knowledge, Raw, Index data, configuration, dependencies, or ROADMAP.
- Do not call external APIs or read/log provider credentials.
- Do not add personal data or the owner's real article content/metadata to tests or Git.
- Do not add a vector database or new dependency.
- Do not broaden scope into general query rewriting or unrelated ranking refactors.

## Acceptance

- A deterministic synthetic `AI部署网页` regression ranks the specific site/deployment document above documents matching only generic `AI` or `网页` terms.
- Existing retrieval tests pass and explanations expose why the specific candidate ranked higher.
- In MAIN's local, read-only check against the owner's current index, the named article appears in the top 10; its personal metadata is not persisted in tests or tracked files.
- No network calls, storage writes, or changes to stored data.

## Completion report

Return TASK, STATUS, changes, modified files, tests and outcomes, unresolved issues, risks, branch, worktree, commit, and acceptance steps. Commit on the assigned task branch before requesting MAIN review.
