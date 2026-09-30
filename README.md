# Personal AI Knowledge Base

把看过的 AI 资料，变成下一次可以直接调用的知识和内容素材。

> 当前版本：V1 本地优先 Streamlit 应用；本机主人免登录，公网访客邀请码隔离已完成本地实现。
>
> 当前认证路线：本机主人免登录＋公网每人一个可撤销、可重复使用的邀请码。正式域名、HTTPS、反向代理、备份和生产部署仍未完成；本地账号密码和 Cloudflare Access 仅保留为历史兼容实现，不是当前主线。

## 它解决什么问题

AI 学习资料通常散落在公众号文章、课程 PDF 和临时笔记里。收藏并不等于掌握：过一段时间之后，很难回忆自己看过什么、不同资料之间有什么关系，也很难把它们重新变成一条有证据的内容。

这个项目把“阅读 -- 理解 -- 综合 -- 创作”放在同一条可追溯链路中：原始资料保留在本地，AI 生成的单篇笔记和主题知识与原文分层保存，检索结果带来源，口播生成前还需要人工确认选题。

对使用者的直接收益是：下一次准备写 AI 提效内容时，不必从零开始搜索，而是从自己的资料、判断和已形成的主题认知出发。

它不是单纯的收藏夹，也不是把所有内容丢进黑盒 RAG 的问答页面；V1 更关注三件事：资料不会被 AI 覆盖、结论能够回到来源、知识最终能够进入内容生产。

## 给其他人使用

当前项目是一个可以下载到本机运行的 Streamlit 网页应用，不是已经部署好的公网网址。其他人下载代码后，可以在自己的电脑上启动网页；资料默认保存在自己的本机，不会自动上传到你的 GitHub 仓库。

GitHub 页面已经提供源码下载入口：打开仓库后点击右上角 `Code`，可以选择 `Download ZIP`。也可以使用命令行克隆：

```bash
git clone https://github.com/liuzihan314-wq/personal-ai-kb.git
cd personal-ai-kb
```

### 最短启动路径

需要 Python 3.12 和 `uv`。如果终端提示 `uv: command not found`，请先按 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/) 安装。

macOS／Linux 可以执行：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell 可以执行：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装完成后重新打开终端，并确认 `uv --version` 能输出版本号，再进入项目目录执行：

```bash
uv sync
uv run pkb health
uv run streamlit run src/pkb/ui/app.py --server.headless true --server.showEmailPrompt false --browser.gatherUsageStats false
```

然后打开 <http://127.0.0.1:8501/>。第一次使用完整 AI 能力时，还需要在网页侧栏配置 AI Provider；只查看页面和使用部分本地检索能力不需要把 API Key 写进代码。

维护者本机可以直接双击 `output/打开知识库.command`。这个启动器只监听 `127.0.0.1`，并强制使用 V1 主人免登录模式；它直接运行 `src/pkb/ui/app.py`，不会维护第二份网页副本，因此后续源码功能更新会自动反映到 command 打开的页面。该启动器不能用于公网分享。

当前仓库已有 [v0.1.0 Release](https://github.com/liuzihan314-wq/personal-ai-kb/releases/tag/v0.1.0)。其他人仍应先按本 README 完成本地安装和健康检查；完整 AI 能力还需要自行配置 Provider 和 API Key。

## 适合哪些人

这个知识库不局限于 AI 学习资料。它更像一个“会整理和检索的本地资料柜”：只要资料能够整理成支持的输入格式，就可以按自己的工作建立知识库。

| 使用者 | 可以存什么 | 可以解决什么问题 |
| --- | --- | --- |
| AI 学习者 | 公众号文章、课程 PDF、实践笔记、观点卡片 | 找回看过的资料，整理主题，生成内容选题和口播 |
| 科研人员 | 论文、研究报告、实验记录、文献笔记 | 按主题查找论文观点，回到原文核对证据，比较不同研究结论 |
| 销售人员 | 经授权导出的聊天记录、客户需求、产品资料、跟进笔记 | 查找客户历史需求，整理常见问题和销售话术依据 |
| 产品与运营人员 | 会议纪要、需求文档、SOP、复盘材料 | 根据历史资料回答问题，沉淀流程和经验 |
| 内容创作者 | 灵感、好句、选题、素材和旧稿 | 从已有素材中发现新选题，减少重复搜索 |

聊天记录目前建议先导出为文本／PDF，或复制到观点卡片中保存；项目暂不承诺直接同步微信、企业微信、CRM 或其他聊天平台。

## 当前边界，一眼看懂

| 维度 | V1 当前状态 |
| --- | --- |
| 运行方式 | 本地文件系统 ＋ Streamlit；macOS 为主，Windows 作为备用兼容环境 |
| 用户模型 | 本机主人免登录；公网访客使用邀请码隔离；本地账号密码仅为历史实验实现 |
| 稳定输入 | 微信公众号文章 URL、正常文本 PDF、观点／好句卡片 |
| 核心输出 | 本地检索、知识问答、主题综合、3～5 个候选选题、人工确认后的 2～3 分钟口播稿 |
| 检索 | 标题、标签、关键词、Topic、Related 和 JSON Index；Web UI 可选 Embedding 语义召回 |
| 云端状态 | 没有当前生产部署；邀请码应用层认证已完成本地实现和 E2E 验证，域名、HTTPS、反向代理、备份和服务器部署仍未完成 |

## V1 闭环：从 Raw 到口播

主链路可以压缩成一句话：

```text
Raw → Notes → Knowledge → Index / Retrieval → 选题 → 人工选择 → 再检索 → 口播
```

![Personal AI Knowledge Base V1 数据流](docs/assets/pkb-v1-flow.svg)

每一层解决不同问题：

| 阶段 | 做什么 | 为什么保留这一层 |
| --- | --- | --- |
| `Raw` | 保存公众号正文、PDF 原文件／文本或用户原始观点 | 它是事实来源，保持不可被 AI 覆盖 |
| `Notes` | 对单篇资料生成摘要、核心观点、好句、标签和来源 | 回答“这一篇讲了什么” |
| `Knowledge` | 把同一主题的多篇 Notes 编译成当前认知 | 回答“关于这个主题，我目前一共知道什么” |
| `Index / Retrieval` | 用标题、标签、关键词、Topic、Related 和 JSON Index 找候选证据 | 让检索可解释、可回到原文；Web UI 可选语义召回 |
| `选题` | 从整个知识库生成 3～5 个 AI 提效方向候选 | 把知识转成可执行的内容方向 |
| `人工选择` | 用户查看依据后明确确认一个候选 | 口播不是无条件自动发布，保留人的判断入口 |
| `再检索` | 围绕已确认选题重新找 Knowledge、Notes、观点卡片和必要 Raw | 写作上下文来自当前证据，而不是只复用第一次候选 |
| `口播` | 生成约 2～3 分钟、自然口语且有来源支撑的稿件 | 形成从知识到内容输出的闭环 |

同一条链路也支持两类中间使用方式：在 `02 Search / Q&A` 中直接查资料或提问，在 `03 Topic synthesis` 中先编译一个主题页。

## 本地检索和 RAG 有什么区别

项目把“找资料”和“让 AI 组织答案”分成两步，不会把所有原文一次性塞给模型。

| 方式 | 工作方式 | 适合场景 | 是否需要调用聊天模型 |
| --- | --- | --- | --- |
| 本地直接检索 | 导入资料时，AI 生成 Note、标签、关键词、Topic 和 Related；本地脚本把这些信息写入 JSON Index，搜索时直接读取 Index 并排序 | 快速找资料、查看来源、没有 API Key 时先检索 | 不需要 |
| RAG／知识库问答 | 先从本地 Index、Notes、Knowledge 和 Raw 中找相关证据，再把选中的证据交给 AI 生成回答，并保留来源链 | 用自然语言提问、跨多篇资料总结、生成主题和口播 | 需要 |
| 可选语义检索 | 在本地检索的基础上，用 Embedding 判断“意思是否相近”，帮助找出用词不同但主题相关的资料 | 同义表达、资料较多、关键词不准确时 | 需要 Embedding 服务；聊天回答仍需聊天 Provider |

这里的“本地检索”不是每次搜索都让 AI 重新阅读全部文件。更像是：导入时先让 AI 给资料贴好标签，之后由本地 Index 像目录卡片一样负责快速查找；RAG 则是在找到资料后，再让 AI 根据这些资料组织答案。

## 界面预览

下面的截图来自本地运行页面。它们展示的是从资料导入、检索问答，到选题和口播生成的主要流程。

<p align="center">
  <img src="docs/assets/screenshots/home.png" alt="Personal AI Knowledge Base 首页" width="48%" />
  <img src="docs/assets/screenshots/search-qa.png" alt="Search / Q&A 检索与问答" width="48%" />
</p>

<p align="center">
  <img src="docs/assets/screenshots/topics.png" alt="候选选题" width="48%" />
  <img src="docs/assets/screenshots/script.png" alt="口播结果" width="48%" />
</p>

## V1 支持什么，不支持什么

### 支持的输入

| 输入 | 当前行为 |
| --- | --- |
| 微信公众号文章 | 只接受 `https://mp.weixin.qq.com/s/...`。先尝试安全的文章正文提取；提取不完整时，保留 URL 并补充标题和正文后再导入。手动公众号文章导入是 V1 稳定入口。 |
| 正常文本 PDF | 使用 PyMuPDF 读取有文本层、可以正常复制文字的 PDF；原始 PDF 与提取文本分开保留。 |
| 观点／好句／灵感卡片 | 手动保存正文；来源 URL、标签和个人备注均可选，并会进入后续 Notes、检索、主题综合和选题流程。 |

### 明确限制

- 不处理扫描 PDF、图片型 PDF，也不做 OCR。
- 不处理视频号内容、微信收藏视频或其他视频输入。
- 不把普通网页 URL／普通链接收藏当作知识输入。观点卡片可以记录一个可选来源 URL，但不会因此抓取该网页。
- 微信收藏自动增量同步仍是 Experimental／POC，不是 V1 主闭环；当前稳定路径是手动提供公众号文章 URL。
- 默认 V1 不开启登录、团队协作、移动 App、自动剪辑、自动配音或自动发布；本机启动器免登录，公网访客路线使用邀请码，必须放在 HTTPS 入口后。本地账号密码和 Cloudflare Access 不属于当前推荐入口。

## 3 分钟演示路径

完整 AI 演示需要先配置一个可用的 AI Provider，并准备不含隐私的公开或合成样本。仓库不附带个人资料，也不会把测试用 Mock 文本伪装成真实回答。

1. 启动本地 Web UI。
2. 在 `01 导入与观点` 中导入一份正常文本 PDF，保存一张观点／好句卡片；再输入一篇自己有权处理的公众号文章 URL。若自动提取失败，补充标题和正文。
3. 打开 `02 Search / Q&A`，先检索一个关键词，再提出一个问题；展开结果查看候选、证据和来源链。
4. 打开 `03 Topic synthesis`，输入一个主题，查看多篇 Notes 被编译后的主题知识和来源。
5. 打开 `04 选题与口播`，生成候选选题，查看每个候选的依据；选择一个候选，点击“确认此选题”，再点击“生成口播”。
6. 在“二次检索”和“来源链”中核对：口播使用的是确认选题后的新一轮证据，而不是没有依据的自由生成。

如果只想验证页面能启动，不配置 Provider 也可以打开 UI；但依赖 AI 的 Notes、主题综合和真实问答／口播不能完成，页面会明确提示配置缺失，不会回退成假回答。

## 本地运行

### Web UI：主要日常入口

在项目根目录执行：

```bash
uv sync
uv run pkb health
uv run streamlit run src/pkb/ui/app.py
```

- `uv sync`：按 `pyproject.toml` 同步 Python 3.12 项目环境；预期是依赖安装完成。
- `uv run pkb health`：读取当前配置并报告应用名、环境和 `data_dir`；预期输出 `status: ok`。
- `uv run streamlit run src/pkb/ui/app.py`：启动本地 Streamlit 页面；预期浏览器打开后看到四个 V1 工作区标签。
- 失败检查：确认当前目录是仓库根目录、Python 满足 `pyproject.toml`、`uv` 可用；若页面提示数据不存在，先导入一份正常文本 PDF 或保存一张观点卡片；若 AI 操作提示 Provider 未配置，按下方配置说明处理。

### CLI：开发、自动化和验收入口

项目通过 `pyproject.toml` 暴露 `pkb` 命令。下面的命令名与当前 Typer 入口一致：

```bash
uv run pkb health
uv run pkb import-pdf ./path/to/article.pdf
uv run pkb add-idea "先验证最小闭环，再扩大输入范围"
uv run pkb import-wechat-article "https://mp.weixin.qq.com/s/example" --title "示例标题" --content "示例正文"
uv run pkb generate-note <document-id>
uv run pkb rebuild-index
uv run pkb search "AI 工作流"
uv run pkb ask "我的知识库中关于 AI 工作流的共同判断是什么？"
uv run pkb generate-topics
uv run pkb write-script "选题标题" --confirm
```

`import-pdf` 和 `add-idea` 负责写入 Raw；使用 CLI 时，通常还要用 `generate-note` 和 `rebuild-index` 完成后续材料准备。`import-wechat-article` 支持公众号 URL 和手动标题／正文回退。CLI 主要用于开发调试、自动化和验收；当前 CLI 的 AI 服务调用仍面向默认的开发／测试组合，不要把其默认输出当作真实模型结果。需要真实 Provider 时，以 Streamlit UI 的配置与四步日常流程为准。

命令失败时先查看 `uv run pkb --help` 和报错中的目标路径，不要把 `.env`、`data/` 或真实资料作为调试输出提交到仓库。

## AI Provider 配置原则

核心业务不写死模型或厂商。Streamlit 侧栏可以填写并保存配置，也可以复制 `.env.example` 到项目根目录的 `.env` 后重启页面：

```bash
cp .env.example .env
```

这条命令的目的，是创建只存在于本机的配置文件；预期是项目根目录出现 `.env`。如果文件已经存在，不要覆盖其中已有配置，改为手动合并变量。

### 必填的聊天 Provider

| 变量 | 作用 |
| --- | --- |
| `PKB_AI_PROVIDER` | 当前接受 `deepseek` 或 `openai-compatible` |
| `PKB_AI_MODEL` | 服务商实际可用的模型名；由配置提供，不写死在 Core |
| `PKB_AI_BASE_URL` | OpenAI-compatible API 根地址；适配器会调用其 `chat/completions` 接口 |
| `PKB_AI_API_KEY` | 本机密钥；只放 `.env` 或页面保存的本机配置，不写入源码 |

### 可选的语义检索

`PKB_EMBEDDING_MODEL`、`PKB_EMBEDDING_BASE_URL` 和 `PKB_EMBEDDING_API_KEY` 必须一起配置，Streamlit UI 才会启用 Embedding 语义召回；三项留空时使用 V1 的直接检索。直接检索依赖标题、标签、关键词、Topic、Related 和 JSON Index，不需要 Vector DB。

配置后的预期结果是：页面可以生成真实 Notes、主题综合、问答和口播，并显示来源链。若返回 HTTP 错误，依次检查 endpoint 是否兼容、模型名是否有效、密钥和账户额度是否正常；不要把 API Key 粘贴进 issue、日志或 Git diff。

需要注意的隐私边界：`Raw` 在本机保存，但配置真实 Provider 后，导入资料会发送到该 Provider 以生成 Notes，问答和口播也会发送当前检索出的上下文。请只处理自己有权使用的资料，并单独评估所选服务商的数据政策；未配置 Provider 时，页面不会把 Mock Provider 的测试文本当作真实回答。

### 当前认证与分享模式

V1 默认 `PKB_AUTH_ENABLED=false`，维护者本机通过 `output/打开知识库.command` 免登录进入自己的知识库。当前公网访客路线是 `invite` 邀请码模式；每个邀请码对应一个独立用户目录，不能多人共用。

认证成功后会生成 `IdentityContext`，并绑定到 `data/users/<user_id>/`。不同邀请码对应的访客不会看到对方的 PDF、笔记、索引、检索来源、问答或历史。

#### 邀请码模式（当前访客路线）

邀请码能力已经完成本地实现和合成 E2E 验证，但正式公网部署仍未完成。每位访客应获得一个独立、可撤销、可重复使用的邀请码；邀请码必须通过私密渠道发送，并且公网入口必须使用 HTTPS。邀请码有两种 API 模式：`shared` 使用主人配置的 API，`byok` 要求访客填写自己的 API。

创建邀请码：

```bash
uv run pkb invite-create --name "张三"
uv run pkb invite-create --name "李四" --api-mode byok
```

命令会输出 `invite_id`、`api_mode` 和一次明文 `code`。`shared` 是默认模式，访客直接使用主人在服务器上配置的 AI 服务；`byok`（Bring Your Own Key）模式下，访客登录后必须在侧边栏填写自己的聊天 Provider 和可选的 Embedding API，系统不会回退使用主人配置。把 `code` 通过私密渠道发给对应访客；系统只在 `config/invites.json` 中保存 PBKDF2 哈希，不保存明文，也不会在 `invite-list` 中再次显示。

查看和撤销邀请码：

```bash
uv run pkb invite-list
uv run pkb invite-revoke i_0123456789abcdef
```

撤销只会停止该邀请码继续登录，并使其现有网页会话在下一次页面运行时失效；不会删除访客数据。邀请码遗失后无法找回原明文，应撤销旧记录并创建一个新邀请码。新邀请码会产生新的独立用户目录，不会自动继承旧邀请码的数据。

公网实例使用以下配置；本机 `output/打开知识库.command` 会显式覆盖为免登录模式，因此不能作为公网启动命令：

```bash
PKB_AUTH_ENABLED=true
PKB_AUTH_MODE=invite
PKB_AUTH_INVITES_FILE=config/invites.json
```

邀请码相当于登录凭据，只能通过 HTTPS 传输。当前实现提供应用层认证和数据目录隔离，但尚未完成域名、HTTPS、反向代理、服务器磁盘备份和正式生产部署。

`byok` 访客在侧边栏填写的 API 只保留在当前网页会话，不写入主人 `.env`、邀请码文件或 Git。请求仍会经过部署知识库的服务器，因此正式公网使用仍必须配置 HTTPS，并应向访客说明这一点。访客如果把项目下载到自己的电脑单独运行，则使用的是自己的本地配置，不需要主人提供 API。

#### 历史兼容实现

- `PKB_AUTH_MODE=local` 的本地账号密码模式曾用于验证双用户隔离，代码仍保留以兼容历史实现，但不再作为当前部署入口、公开使用路径或后续验收目标。
- `PKB_AUTH_MODE=cloudflare` 的 Cloudflare Access 适配器也仍保留，但正式 Access、腾讯云和生产域名部署没有继续完成，不应在项目已经部署前对外宣称可用。

## 数据目录与安全边界

默认 `data_dir` 是项目根目录下的 `data/`；也可以通过配置中的 `PKB_DATA_DIR` 改为其他本地目录。典型结构如下：

```text
data/
├── raw/                 # 原始 PDF、提取文本、公众号正文和观点卡片；事实来源
├── notes/               # 单篇 AI 理解结果，Markdown + YAML Frontmatter
├── knowledge/           # 多篇 Notes 编译的主题知识，Markdown
├── index/               # 本地 JSON Index，例如 index.json
├── cache/               # 本地缓存预留
└── logs/                # 本地日志预留
```

- `Raw`、`Notes`、`Knowledge` 和 `Index` 分层保存，AI 不能用 Notes 或 Knowledge 覆盖 Raw。
- `.gitignore` 排除 `.env`、`data/`、`runtime/` 和 `output/`；不要执行 `git add .` 来绕过逐项复核。
- 默认 V1 没有加密和公开服务的安全边界；本机主人启动器只绑定 `127.0.0.1`。邀请码实例必须单独部署在 HTTPS 入口后，不要把免登录 Streamlit 直接暴露到公网。
- 主人模式下，页面保存的 `.env` 会限制为当前系统用户可读写；Provider 密钥以密码输入、不显示、不写日志。`byok` 访客模式不写入 `.env`，只保留当前网页会话。以上措施不替代操作系统权限和服务商侧的密钥管理。

## 后续部署规划：Cloudflare Access ＋ 腾讯云（非当前入口）

这一节是保留的历史部署方案，不是当前公网能力声明。当前访客路线以邀请码应用层认证为准；Cloudflare Access、腾讯云、生产域名和正式多用户部署没有继续完成，也不是当前 Release 的使用前提。

目标部署链路是：

```text
浏览器 → Cloudflare Access（HTTPS / 登录）
       → 腾讯云上的 Streamlit 应用
       → 应用校验身份与角色
       → data/users/<user_id>/{raw,notes,knowledge,index,...}
```

最小验证切片只先验证两个身份：管理员 A 和普通成员 B。

- Access 负责入口和登录；应用计划读取受信的身份信息，校验唯一用户标识与角色，缺少或非法身份时拒绝请求。
- 每个用户的 `raw`、`notes`、`knowledge`、`index`、问答／选题／口播历史写入独立用户根目录，不回退到共享用户目录。
- A 与 B 需要在资料列表、检索、问答来源、下载和历史记录上互相隔离；管理员能力是否包含全局查看，先由 V2 设计任务明确，不能凭部署默认获得。
- 本机主人免登录和邀请码隔离是当前保留路线；如果未来重新启动 Cloudflare Access 部署，必须另立任务，重新确认身份提供商、域名、数据迁移和回滚边界。

Cloudflare 的具体身份提供商、域名、腾讯云实例规格、持久化方案和生产凭据目前尚未确定。它们需要在文档对齐和双身份测试通过后，由维护者单独确认，不在本 README 中伪装成已经部署。

## 技术栈

- Python 3.12 ＋ `uv`：跨平台核心运行环境。
- Streamlit：V1 日常 Web UI；Typer：CLI、自动化和验收入口。
- PyMuPDF：正常文本 PDF 提取；扫描 PDF／OCR 不在 V1。
- 本地文件系统：Raw 为事实来源，Notes／Knowledge 使用 Markdown + YAML Frontmatter，Index 使用 JSON。
- 可插拔 AI Provider：标准库 HTTP 调用 OpenAI-compatible `chat/completions`；不绑定某家 SDK。
- V1 Retrieval：可解释的标题、标签、关键词、Topic、Related、Index 检索；Web UI 可选 Embedding，不依赖 Vector DB。
- `pytest`：回归测试；Python logging：本地日志。

## 设计文档

- [PRODUCT.md](PRODUCT.md)：产品范围、输入、输出与数据原则
- [ARCHITECTURE.md](ARCHITECTURE.md)：数据流、分层与模块边界
- [TECH_STACK.md](TECH_STACK.md)：技术选型与适用范围
- [ROADMAP.md](ROADMAP.md)：任务依赖、验收标准与里程碑
- [CODEX_HANDOFF.md](CODEX_HANDOFF.md)：MAIN／Worker 协作和 Git 约定

## 开发检查

```bash
uv run pytest
```

目的：运行当前项目的回归测试；预期是所有现有测试通过。若失败，先确认依赖已由 `uv sync` 同步，再根据失败模块定位；文档或素材变更不应修改 `src/`、`tests/` 或 V1 行为。
