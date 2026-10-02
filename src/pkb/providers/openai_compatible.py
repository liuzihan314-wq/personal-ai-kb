"""Small OpenAI-compatible chat-completions adapter with no vendor SDK."""

import json
from collections.abc import Callable, Mapping, Sequence
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from pkb.providers.protocol import (
    DocumentInput,
    ProviderDocument,
    RelatedLink,
    TopicSuggestion,
    VisualMaterialSuggestion,
)


class ProviderRequestError(RuntimeError):
    """Raised when a configured provider rejects or cannot complete a request."""


Transport = Callable[[str, Mapping[str, str], Mapping[str, object]], Mapping[str, object]]


def _document(value: DocumentInput) -> ProviderDocument:
    return value if isinstance(value, ProviderDocument) else ProviderDocument(content=value)


def _context(documents: Sequence[ProviderDocument]) -> str:
    blocks = []
    for index, item in enumerate(documents, start=1):
        identity = item.document_id or f"source-{index}"
        title = item.title or identity
        citation_id = item.citation_id or f"来源 {index}"
        blocks.append(f"[{citation_id}: {title} | {identity}]\n{item.content}")
    return "\n\n".join(blocks)


def _script_context(documents: Sequence[ProviderDocument]) -> str:
    """Format writing material without source numbers leaking into the script."""

    blocks = []
    for item in documents:
        title = item.title or item.document_id or "背景材料"
        blocks.append(f"【{title}】\n{item.content}")
    return "\n\n".join(blocks)


class OpenAICompatibleProvider:
    """Call an OpenAI-compatible ``/chat/completions`` endpoint safely."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 60.0,
        transport: Transport | None = None,
    ) -> None:
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        if not self.model or not self.base_url or not self.api_key:
            raise ValueError("model, base_url, and api_key are required")

    @property
    def endpoint(self) -> str:
        suffix = "/chat/completions"
        return self.base_url if self.base_url.endswith(suffix) else self.base_url + suffix

    def _default_transport(
        self,
        url: str,
        headers: Mapping[str, str],
        body: Mapping[str, object],
    ) -> Mapping[str, object]:
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            with urlopen(  # noqa: S310
                request,
                timeout=self.timeout_seconds,
                context=ssl_context,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise ProviderRequestError(f"AI Provider returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderRequestError("AI Provider request failed") from exc
        if not isinstance(payload, Mapping):
            raise ProviderRequestError("AI Provider returned a non-object response")
        return payload

    def _complete(self, system: str, prompt: str) -> str:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = (self._transport or self._default_transport)(self.endpoint, headers, body)
        try:
            choices = payload["choices"]
            message = choices[0]["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderRequestError("AI Provider response has no assistant content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderRequestError("AI Provider returned empty assistant content")
        return content.strip()

    def _json_list(self, system: str, prompt: str, *, allow_fence: bool = False) -> list[Any]:
        value = self._complete(system, prompt)
        if allow_fence and value.startswith(("```json\n", "```\n")) and value.endswith("\n```"):
            value = value.split("\n", 1)[1].rsplit("\n", 1)[0]
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ProviderRequestError("AI Provider did not return the requested JSON list") from exc
        if not isinstance(parsed, list):
            raise ProviderRequestError("AI Provider did not return a JSON list")
        return parsed

    def summarize(self, document: DocumentInput) -> str:
        item = _document(document)
        return self._complete(
            "你是中文知识库编辑。只基于给定文本，输出一段准确、简洁的中文摘要。",
            f"标题：{item.title or ''}\n\n文本：\n{item.content}",
        )

    def extract_key_points(self, document: DocumentInput) -> list[str]:
        item = _document(document)
        values = self._json_list(
            "你是中文知识库编辑。只基于给定文本，返回 3 到 5 条关键点。只输出 JSON 字符串数组。",
            f"标题：{item.title or ''}\n\n文本：\n{item.content}",
        )
        return [value.strip() for value in values if isinstance(value, str) and value.strip()]

    def extract_quotes(self, document: DocumentInput) -> list[str]:
        item = _document(document)
        values = self._json_list(
            "你是中文知识库编辑。只摘取给定文本中可直接引用的原句，最多 3 条。只输出 JSON 字符串数组；没有则输出 []。",
            f"标题：{item.title or ''}\n\n文本：\n{item.content}",
        )
        return [value.strip() for value in values if isinstance(value, str) and value.strip()]

    def generate_tags(self, document: DocumentInput) -> list[str]:
        item = _document(document)
        values = self._json_list(
            "你是中文知识库编辑。只基于给定文本生成 3 到 6 个简短标签。只输出 JSON 字符串数组。",
            f"标题：{item.title or ''}\n\n文本：\n{item.content}",
        )
        return [value.strip() for value in values if isinstance(value, str) and value.strip()]

    def link_related(
        self,
        document: ProviderDocument,
        candidates: Sequence[ProviderDocument] = (),
    ) -> list[RelatedLink]:
        if not candidates:
            return []
        values = self._json_list(
            "只根据来源文本判断关联。返回最多 5 项 JSON 数组，每项含 document_id、score（0 到 1）、reason。",
            f"当前资料：\n{_context([document])}\n\n候选资料：\n{_context(candidates)}",
        )
        links = []
        for value in values:
            if isinstance(value, dict):
                try:
                    links.append(RelatedLink.model_validate(value))
                except ValueError:
                    continue
        return links

    def compile_topic(self, topic: str, notes: Sequence[ProviderDocument] = ()) -> str:
        return self._complete(
            "你是中文知识库编辑。只基于给定 Notes，综合当前共识、分歧和可行动结论；资料不足时明确说明。",
            f"主题：{topic}\n\nNotes：\n{_context(notes)}",
        )

    def answer_question(self, question: str, context: Sequence[ProviderDocument] = ()) -> str:
        return self._complete(
            "你是中文知识库问答助手。只能使用提供的本地来源回答；不要臆造外部事实。直接回答问题，分点说明；资料不足时明确说不足。引用证据时必须使用资料块中方括号内的来源编号，格式为 [来源 1]；只能引用实际提供的编号，不得编造编号或引用未提供的来源。",
            f"问题：{question}\n\n本地来源：\n{_context(context)}",
        )

    def generate_topics(
        self,
        context: Sequence[ProviderDocument] = (),
        *,
        limit: int = 3,
    ) -> list[TopicSuggestion]:
        values = self._json_list(
            (
                f"你是中文自媒体选题编辑。根据给定材料提出最多 {limit} 个具体选题。"
                "每题只讲一个观众问题、做法或取舍，标题自然、有吸引力、可直接发布。"
                "禁止把主题标签用 ×、+ 或泛泛的‘可执行流程’强行拼接；禁止用 card、idea、"
                "AI使用技巧等类型或宽泛标签充当选题。不要倒序重复或换个说法重复同一题。"
                "资料支持不足时少出题，不凑满数量。一篇内容充分的材料也可以独立支撑一个选题。"
                "只输出合法 JSON 数组，不要 Markdown 代码围栏或说明文字，每项含 title、rationale、focus、source_ids。"
                "focus 必须是材料原文出现的一个具体连续短语，例如‘声音克隆’、‘worktree’；"
                "不是‘AI’、‘AI视频’等宽泛分类。source_ids 是实际使用的材料 ID 数组，"
                "只能从给定 ID 中选择，每份选中的材料都必须直接支持 focus。"
            ),
            _context(context),
            allow_fence=True,
        )
        suggestions = []
        for value in values:
            if isinstance(value, dict):
                try:
                    suggestions.append(TopicSuggestion.model_validate(value))
                except ValueError:
                    continue
        return suggestions[:limit]

    def plan_visual_materials(self, topic: str, paragraphs: Sequence[str]) -> list[VisualMaterialSuggestion]:
        values = self._json_list(
            "你是给新手创作者安排实拍素材的中文视频编辑。只围绕已经定稿的口播，提出 3 到 5 项可执行的演示建议，"
            "不要改写口播、不要逐句重复，优先录屏、前后对比、操作过程与简单字幕卡。"
            "每项给出对应 paragraph（实际段落编号）、visual（拍什么画面）、preparation（1 到 5 个具体操作步骤的字符串数组）、"
            "tool（优先当前 AI 网页、系统录屏、现有剪辑工具等类别）、alternative（拍不到时的静态截图或字幕卡方案）。"
            "必须说清展示的输入、操作、观察什么；不能只写‘配 AI 画面’或‘网上找素材’。"
            "AI 写作题可用同一主题的简单提示词与补充背景后的提示词作对比，但真实结果要用户实际运行，不能编造结果或保证效果。"
            "所有图片和视频都只是需要用户制作的建议，不得声称已录好、可直接下载或已在知识库找到视频；不要提供虚构链接、文件或实验数据。"
            "不要推荐额外安装收费软件或不熟悉的工具，涉及公开录屏时提示隐藏账号、密钥和私人信息。"
            "演示配置文件或真实对话时，优先使用脱敏的示例副本；不要要求修改创作者正在使用的正式配置。"
            "只返回合法 JSON 数组，不要代码围栏或说明文字，所有字段均必须非空。",
            f"选题：{topic}\n已定稿的口播：\n" + "\n\n".join(f"第 {i} 段：{text}" for i, text in enumerate(paragraphs, 1)),
            allow_fence=True,
        )
        return [VisualMaterialSuggestion.model_validate(item) for item in values]

    def write_script(
        self,
        topic: str,
        context: Sequence[ProviderDocument] = (),
        *,
        target_seconds: int = 150,
    ) -> str:
        return self._complete(
            (
                "你是中文自媒体口播编剧。根据给定背景材料写一篇可以直接录制的视频口播稿，"
                "不是知识库问答，也不是资料摘要。全文使用自然口语和短句，直接对观众说话。"
                "开头两句话必须有钩子，可使用反常识判断、痛点或结果承诺，但不能捏造事实。"
                "你必须自己创作开场，不必等待原文提供痛点或钩子，也不要求逐句参考原文章。"
                "先从选题中找出观众想完成的事和卡住的地方，用具体场景、成本或取舍吸引观众。"
                "例如节省 token 的选题可从‘每次提问都把整段聊天塞进去，先看看哪些背景真的需要。’切入；"
                "不要照抄示例，要为当前选题写独立开场，不限定开头词或问句形式。"
                "中段围绕一个主线展开，用自然转折串联具体观点和做法；结尾给出明确收束或行动建议。"
                "输出 700 到 900 个中文字符，不要标题、提纲、Markdown 列表或写作说明。"
                "正文禁止出现‘来源一’‘来源二’‘来源三’‘Raw’‘Note’‘Knowledge’"
                "‘本地检索’‘根据资料’等知识库内部措辞，也不要向观众解释证据链。"
                "不要出现‘本文’‘本篇’‘第几篇’‘系列导航’或材料标题；不要复制摘要、逐篇介绍文章。"
                "整篇只围绕确认的问题展开，不能因为材料都含 AI 就串入别的领域。"
                "先确定一个具体场景，再解释做法和取舍；用具体细节替代‘先跑通闭环’等套话。"
                "不要用省略号截断引用或凑字数，不要承诺未经验证的流量、效果或收益。"
                "材料用于支撑事实和具体方法；允许自主设计表达、类比、转场、收尾以及明确标注的假设场景。"
                "事实性主张仍须有材料依据，不得编造真实案例、个人经历、数字、工具能力或效果承诺。"
            ),
            f"口播主题：{topic}\n目标时长：{target_seconds} 秒\n\n背景材料：\n{_script_context(context)}",
        )
