from pkb.providers import AIProvider, MockAIProvider, ProviderDocument


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
