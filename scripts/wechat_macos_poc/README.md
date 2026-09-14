# WeChat macOS POC

这是隔离的、只读 metadata-only 可行性探针目录，不是正式 WeChat Adapter。

## 目录约定

- `classifier.py`：纯函数分类规则；不访问微信、网络或文件系统。
- `observation.py`：只读取候选文件的大小、修改时间、SQLite header 和只读打开结果；不查行、不解密、不复制、不写结果。
- `probe.py`：只运行内置 synthetic metadata 样本；不接受真实数据输入、不写输出文件。
- `README.md`：记录安全边界和当前 POC 限制，不保存真实观察数据。
- 文件名使用英文；样本只允许使用 `synthetic-*` 占位值。
- 禁止在此目录保存正文、真实 URL、账号信息、数据库副本、凭据或运行缓存。

## 当前结论边界

合成分类测试只证明 deny-by-default 白名单规则的行为，不证明微信原生字段存在，也不证明真实收藏能被读取、分类、提取、去重或重启后恢复。真实 POC 结论以 `output/TASK-013-wechat-macos-poc.md` 为准；当前结论为 `BLOCKED`。
