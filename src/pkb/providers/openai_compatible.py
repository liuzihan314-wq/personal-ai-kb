"""Small OpenAI-compatible chat-completions adapter with no vendor SDK."""

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pkb.providers.protocol import (
    DocumentInput,
    ProviderDocument,
    RelatedLink,
    TopicSuggestion,
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
        blocks.append(f"[来源 {index}: {title} | {identity}]\n{item.content}")
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
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
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

    def _json_list(self, system: str, prompt: str) -> list[Any]:
        value = self._complete(system, prompt)
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
            "你是中文知识库问答助手。只能使用提供的本地来源回答；不要臆造外部事实。直接回答问题，分点说明；资料不足时明确说不足。",
            f"问题：{question}\n\n本地来源：\n{_context(context)}",
        )

    def generate_topics(
        self,
        context: Sequence[ProviderDocument] = (),
        *,
        limit: int = 3,
    ) -> list[TopicSuggestion]:
        values = self._json_list(
            f"基于本地来源提出最多 {limit} 个中文内容选题。只输出 JSON 数组，每项含 title、rationale。",
            _context(context),
        )
        suggestions = []
        for value in values:
            if isinstance(value, dict):
                try:
                    suggestions.append(TopicSuggestion.model_validate(value))
                except ValueError:
                    continue
        return suggestions[:limit]

    def write_script(
        self,
        topic: str,
        context: Sequence[ProviderDocument] = (),
        *,
        target_seconds: int = 150,
    ) -> str:
        return self._complete(
            "你是中文口播编辑。只使用本地来源，写清晰、有节奏的口播稿；不要加入未给出的事实。",
            f"主题：{topic}\n目标时长：{target_seconds} 秒\n\n本地来源：\n{_context(context)}",
        )
