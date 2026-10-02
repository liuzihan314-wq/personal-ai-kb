import json
import ssl
import pytest

from pkb.config import Settings
from pkb.providers import (
    AIProvider,
    MockAIProvider,
    OpenAICompatibleProvider,
    ProviderDocument,
    UnconfiguredProvider,
    configured_provider,
    provider_from_values,
)
from pkb.providers import openai_compatible


def test_script_prompt_allows_original_expression_with_grounded_facts():
    captured = {}

    def transport(url, headers, body):
        captured.update(body=body)
        return {"choices": [{"message": {"content": "原创口播"}}]}

    provider = OpenAICompatibleProvider(model="test", base_url="https://example.test/v1", api_key="test", transport=transport)
    provider.write_script("节省 token", [ProviderDocument(content="只传入当前任务相关背景。")])
    instruction = captured["body"]["messages"][0]["content"]
    assert "你必须自己创作开场" in instruction
    assert "明确标注的假设场景" in instruction
    assert "不得编造真实案例" in instruction
    assert "只使用材料中能够支持的事实，不补充材料之外的数据和结论" not in instruction


@pytest.mark.parametrize("wrapper", ["{body}", "```json\n{body}\n```", "```\n{body}\n```"])
def test_editorial_topics_accept_only_complete_json_arrays(wrapper):
    payload = json.dumps([{"title": "声音克隆怎么少走弯路？", "rationale": "参考音频质量", "focus": "声音克隆", "source_ids": ["voice"]}], ensure_ascii=False)
    provider = OpenAICompatibleProvider(model="test", base_url="https://example.test/v1", api_key="test", transport=lambda *_: {"choices": [{"message": {"content": wrapper.format(body=payload)}}]})
    result = provider.generate_topics([ProviderDocument(document_id="voice", content="声音克隆")])
    assert result[0].focus == "声音克隆" and result[0].source_ids == ["voice"]


def test_editorial_topics_reject_prose_and_malformed_json():
    from pkb.providers.openai_compatible import ProviderRequestError

    provider = OpenAICompatibleProvider(model="test", base_url="https://example.test/v1", api_key="test", transport=lambda *_: {"choices": [{"message": {"content": "下面是候选：[]"}}]})
    with pytest.raises(ProviderRequestError):
        provider.generate_topics()


def test_visual_plan_prompt_uses_actual_script_paragraphs():
    captured = {}
    item = dict(paragraph=1, visual="同一主题两种提示词的真实结果对比", preparation=["输入同一主题并实际生成。"], tool="当前 AI 网页", alternative="制作两张输入截图。")

    def transport(url, headers, body):
        captured.update(body=body)
        return {"choices": [{"message": {"content": json.dumps([item] * 3, ensure_ascii=False)}}]}

    provider = OpenAICompatibleProvider(model="test", base_url="https://example.test/v1", api_key="test", transport=transport)
    result = provider.plan_visual_materials("AI 写作", ["先给读者和场景，再明确要求。"])
    assert len(result) == 3 and result[0].paragraph == 1
    system, prompt = captured["body"]["messages"]
    assert "不能编造结果" in system["content"]
    assert "不得声称已录好" in system["content"]
    assert "第 1 段：先给读者和场景，再明确要求。" in prompt["content"]


def test_mock_provider_implements_protocol_and_supports_summary_call():
    provider = MockAIProvider()
    document = ProviderDocument(
        document_id="doc-1",
        title="Provider abstraction",
        content="A provider keeps model details outside the core.",
    )

    summary = provider.summarize(document)

    assert isinstance(provider, AIProvider)
    assert summary == "Mock summary: A provider keeps model details outside the core."
    assert provider.calls == ["summarize"]


def test_mock_provider_allows_deterministic_response_overrides():
    provider = MockAIProvider(
        responses={
            "answer_question": "The answer comes from the supplied context.",
        }
    )

    answer = provider.answer_question("What is the source?", ())

    assert answer == "The answer comes from the supplied context."
    assert provider.calls == ["answer_question"]


def test_configured_provider_uses_openai_compatible_chat_completions_contract():
    captured: dict[str, object] = {}

    def transport(url, headers, body):
        captured.update(url=url, headers=headers, body=body)
        return {"choices": [{"message": {"content": "只基于本地资料的回答。"}}]}

    provider = OpenAICompatibleProvider(
        model="deepseek-test",
        base_url="https://api.example.test/v1",
        api_key="test-key",
        transport=transport,
    )

    answer = provider.answer_question(
        "资料说了什么？",
        [ProviderDocument(document_id="note-1", title="本地 Note", content="本地内容")],
    )

    assert answer == "只基于本地资料的回答。"
    assert captured["url"] == "https://api.example.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == "deepseek-test"
    assert captured["body"]["stream"] is False
    messages = captured["body"]["messages"]
    assert "只能引用实际提供的编号" in messages[0]["content"]
    assert "[来源 1: 本地 Note | note-1]" in messages[1]["content"]


def test_answer_context_uses_source_chain_citation_id():
    assert openai_compatible._context(
        [
            ProviderDocument(
                document_id="note-1",
                title="本地 Note",
                content="本地内容",
                citation_id="来源 3",
            )
        ]
    ) == "[来源 3: 本地 Note | note-1]\n本地内容"


def test_script_prompt_requests_publishable_spoken_copy_without_source_labels():
    captured: dict[str, object] = {}

    def transport(url, headers, body):
        captured.update(url=url, headers=headers, body=body)
        return {"choices": [{"message": {"content": "可直接录制的口播稿"}}]}

    provider = OpenAICompatibleProvider(
        model="deepseek-test",
        base_url="https://api.example.test/v1",
        api_key="test-key",
        transport=transport,
    )

    provider.write_script(
        "AI 视频",
        [ProviderDocument(document_id="doc-1", title="视频路线", content="先拆流程。")],
        target_seconds=180,
    )

    messages = captured["body"]["messages"]
    system = messages[0]["content"]
    prompt = messages[1]["content"]
    assert "中文自媒体口播编剧" in system
    assert "开头两句话必须有钩子" in system
    assert "700 到 900 个中文字符" in system
    assert "禁止出现" in system
    assert "[来源 1" not in prompt
    assert "【视频路线】" in prompt


def test_provider_default_transport_uses_certifi_tls_context(monkeypatch):
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

    def fake_urlopen(request, *, timeout, context):
        captured["request"] = request
        captured["timeout"] = timeout
        captured["context"] = context
        return Response()

    monkeypatch.setattr(openai_compatible, "urlopen", fake_urlopen)
    provider = OpenAICompatibleProvider(
        model="test-model",
        base_url="https://api.example.test/v1",
        api_key="test-key",
    )

    assert provider.answer_question("question") == "ok"
    assert isinstance(captured["context"], ssl.SSLContext)
    assert captured["context"].verify_mode == ssl.CERT_REQUIRED
    assert captured["context"].check_hostname


def test_provider_selection_never_falls_back_to_mock_when_configuration_is_absent():
    missing = Settings(_env_file=None)
    configured = Settings(
        _env_file=None,
        ai_provider="deepseek",
        ai_model="deepseek-test",
        ai_base_url="https://api.example.test/v1",
        ai_api_key="test-key",
    )

    assert isinstance(configured_provider(missing), UnconfiguredProvider)
    provider = configured_provider(configured)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "deepseek-test"


def test_session_provider_values_create_a_real_provider_without_settings_file():
    provider = provider_from_values(
        "openai-compatible",
        "custom-model",
        "https://api.example.test/v1",
        "session-only-key",
    )

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "custom-model"
