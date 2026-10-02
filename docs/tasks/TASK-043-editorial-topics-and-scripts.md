# TASK-043｜选题与口播质量修复

主人已确认四项施工范围；当前 MAIN 对话执行，独立分支 `codex/task-043-content-quality`，不创建额外聊天或后台实现 Agent。

## 目标与范围

- 每次页面交互检查当前用户资料版本。变化后清除候选、确认和旧稿，提示重新生成；没有轮询定时器。
- 使用已有 Provider.generate_topics 从最新笔记的内容提出具体问题，返回明确的资料 ID 与主线。验证资料 ID、事实支持、标题和重复候选，禁止类型标签或宽泛主题交叉凑题。
- 写稿以候选主线及已选资料 ID 进行新检索和材料筛选，不把无关的开发配置与视频制作一起送给模型；口播与来源展示分离。
- 检查字数、开场、文章介绍与来源字段泄漏、主线相关性。一次针对性重写仍不合格则返回 quality_failed，无摘要拼接兜底。

允许修改 topics、scripts、Provider 选题／写稿提示、UI services／app、相关测试与 README；MAIN 同步 ROADMAP。禁止修改 .env、认证、用户目录、资料、依赖和公网部署。

## 检查点与验收

1. 用声音克隆和 worktree 两组固定合成材料验证候选分开、来源 ID 合法、card／idea 不成为选题、重复题不占位。
2. 模拟新增笔记与重新生成，验证旧选题与确认失效、新资料进入模型上下文；资料更新只在交互时检查。
3. 模拟一次不合格稿再正确重写、连续两次不合格、服务错误、无来源与无关来源；不得把失败状态显示成成功成稿。
4. 定向测试与全量回归、CLI 检查；在目标运行实例用现有真实资料生成候选并选择一个明确方向，生成自然中文口播，检查钩子、主线、正文无文章介绍和资料字段、字数与来源。

不新增第三方依赖；复用已有 Python、Pydantic、Streamlit AppTest 与 Provider。UI 截图原样导出至主项目 output，不上传用户资料。不推送 GitHub。

## 当前台账

Task：TASK-043；Thread：当前 MAIN 对话；Branch：codex/task-043-content-quality；Worktree：/Users/mac/.codex/worktrees/task-043-content-quality/personal-ai-kb-spec；Status：IN_PROGRESS。
