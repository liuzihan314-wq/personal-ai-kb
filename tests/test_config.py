from pathlib import Path

from pkb.config import Settings


def test_default_settings_are_local_and_non_secret():
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
    assert "api_key" not in Settings.model_fields
    assert "base_url" not in Settings.model_fields


def test_settings_load_utf8_dotenv_and_keep_unknown_provider_fields_ignored(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "PKB_APP_NAME=个人知识库\n"
        "PKB_DATA_DIR=workspace\n"
        "PKB_AI_API_KEY=must-not-become-an-app-setting\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "个人知识库"
    assert settings.data_dir == Path("workspace")
    assert "api_key" not in Settings.model_fields
