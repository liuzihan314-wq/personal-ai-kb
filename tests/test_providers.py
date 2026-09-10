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
