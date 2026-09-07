from pathlib import Path

from pkb.config import Settings


def test_default_settings_are_local_and_non_secret(monkeypatch):
    monkeypatch.delenv("PKB_AI_API_KEY", raising=False)

    settings = Settings(_env_file=None)

    assert settings.data_dir == Path("data")
    assert settings.data_directories == (
        Path("data/raw"),
        Path("data/notes"),
        Path("data/knowledge"),
        Path("data/index"),
        Path("data/cache"),
        Path("data/logs"),
    )
    assert settings.ai_provider is None
    assert settings.ai_model is None
    assert settings.ai_base_url is None
    assert settings.ai_api_key is None


def test_settings_load_utf8_dotenv_and_mask_provider_secret(tmp_path):
    env_file = tmp_path / ".env"
    sentinel = "test-only-not-a-secret"
    env_file.write_text(
        "PKB_APP_NAME=个人知识库\n"
        "PKB_DATA_DIR=workspace\n"
        "PKB_AI_PROVIDER=local-test\n"
        "PKB_AI_MODEL=test-model\n"
        "PKB_AI_BASE_URL=http://localhost:9999\n"
        f"PKB_AI_API_KEY={sentinel}\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "个人知识库"
    assert settings.data_dir == Path("workspace")
    assert settings.ai_provider == "local-test"
    assert settings.ai_model == "test-model"
    assert settings.ai_base_url == "http://localhost:9999"
    assert settings.ai_api_key is not None
    assert settings.ai_api_key.get_secret_value() == sentinel
    assert sentinel not in repr(settings)
    assert sentinel not in settings.model_dump_json()
