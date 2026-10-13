# 云端资料独立备份到 Mac

备份使用现有 Streamlit 官方 `st.App` 路由，通过 HTTPS 下载，不需要 Codex 在线或 SSH 通道。云端为日常资料源，Mac 保存独立、经过校验的快照；不自动改动本机知识库数据。

## 备份范围与保存位置

- 保存 Raw 原文／PDF、Notes、Knowledge、Index 和 History，保留原始文件字节、资料 ID、来源关系和目录结构。
- 不备份 API 配置、密钥、邀请码、日志、缓存或其他数据根目录。
- 快照：项目 `data/cloud-backup/<timestamp>/`，其中 `manifest.json` 记录云端根目录、相对路径、大小、SHA-256 和快照指纹。
- 状态：项目 `runtime/cloud-backup/status.json`；定时日志：同目录的 `schedule.log` 和 `schedule-error.log`。
- 传输中间文件：项目 `.tmp/cloud-backup/`，失败下载不发布为快照。
- 无变化时检查现有本机快照完整性，不新增副本；有变化时追加，不覆盖／删除旧快照或本机原资料。

## 运行与安全

服务器入口为 `python -m pkb.cloud_app`，网页与 `/api/backup/manifest`、`/api/backup/snapshot` 使用同一 HTTPS 域名和 Streamlit 官方路由。

云端通过私密变量 `PKB_BACKUP_TOKEN` 配置专用密钥；Mac 仅在用户凭据文件 `~/.config/personal-ai-kb/cloud-backup.key` 中保留对应密钥，权限应为 600。密钥只通过 Authorization 头发送，不放 URL、不输出日志、不进入 Git。缺少／错误密钥不能读取清单或下载；客户端拒绝 HTTP 和重定向。

Mac 用户定时任务 `com.personal-ai-kb.cloud-backup` 每 3600 秒检查一次，登录加载时也检查。关机、睡眠、断网期间不保证运行，恢复后按调度继续；不要把启动任务理解为实时同步。任务失败保留上次成功记录，下一次再尝试。日常无需打开 Codex。

下载会消耗云端网络资源，可能唤醒休眠服务。快照和中间文件不会自动清理，磁盘用量会随资料变化增长；清理或恢复需要单独确认。

## 手动检查

在项目根目录执行：

```bash
.venv/bin/python scripts/cloud_backup.py --status
```

目的：查看最近检查、最近成功时间和快照目录。预期 `success` 或 `unchanged`，并有 `snapshot` 路径。`failed` 表示最近检查失败，旧 `last_success` 不能证明最新云端变化已经备份。

需要立即备份时执行：

```bash
.venv/bin/python scripts/cloud_backup.py
```

预期输出保存的快照目录，或“Cloud unchanged”。失败时检查网络、Railway 服务状态和专用密钥权限；HTTP 401 通常表示两端密钥不一致，HTTP 503 表示数据暂时无法稳定导出或服务不可用，HTTP 429 表示另一个导出正在进行。不要把密钥发到聊天里。

## 暂停与恢复任务

先查询当前用户 ID：

```bash
id -u
```

把输出数字替换下面的 `USER_ID`。暂停：

```bash
launchctl bootout gui/USER_ID/com.personal-ai-kb.cloud-backup
```

目的：停止定时检查，备份文件保留。恢复：

```bash
launchctl bootstrap gui/USER_ID ~/Library/LaunchAgents/com.personal-ai-kb.cloud-backup.plist
```

预期任务重新加载并执行一次检查。若提示已经加载，先查询任务状态；不要重复安装或覆盖 plist。

## 将来整合到 Mac 本地知识库

快照保留完整资料，满足后续恢复／整合需要，但不是把云端绝对路径原样作为本地路径使用。

1. 在独立恢复目录读取快照清单，重新核对每个文件的大小和 SHA-256。
2. 原文与 PDF 原样保留；只把 Raw 元数据、Notes 来源和 Index 中的云端根目录改为恢复目录。
3. 核对 Raw、Note、PDF 和知识页的引用都指向有效文件，重建检索索引。
4. 用真实查询验证可检索、原文可打开、PDF 可预览。
5. 按资料 ID 判断重复／冲突；正式并入原本机目录前确认具体范围，保留两边原件。

正式整合尚需单独执行，不自动把本地旧资料变成云端副本，也不传播云端删除操作。

## 工具依据

- [Streamlit 官方自定义路由 API](https://docs.streamlit.io/1.63.0/develop/api-reference/server/st.app)
- [Railway 官方磁盘文件下载](https://docs.railway.com/cli/volume)：当前官方通道依赖 SSH/SFTP；本实例在当前网络实测连接中断，故使用经授权的 HTTPS 接口。
- [Apple 用户定时任务](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
