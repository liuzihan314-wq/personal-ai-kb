from typer.testing import CliRunner

from pkb.cli.main import app


runner = CliRunner()


def test_hello_command_has_expected_default_output():
    result = runner.invoke(app, ["hello"])

    assert result.exit_code == 0, result.output
    assert result.output == "Hello, World!\n"


def test_hello_command_accepts_name():
    result = runner.invoke(app, ["hello", "--name", "主人"])

    assert result.exit_code == 0, result.output
    assert result.output == "Hello, 主人!\n"


def test_health_command_reports_configured_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("PKB_ENVIRONMENT", "test")
    monkeypatch.setenv("PKB_DATA_DIR", str(tmp_path / "knowledge"))

    result = runner.invoke(app, ["health"])

    assert result.exit_code == 0, result.output
    assert "status: ok" in result.output
    assert "environment: test" in result.output
    assert f"data_dir: {tmp_path / 'knowledge'}" in result.output
    assert "api_key" not in result.output.lower()


def test_health_command_warns_about_duplicate_user_roots(monkeypatch, tmp_path):
    data_dir = tmp_path / "knowledge"
    user_id = "u_" + "a" * 64
    (data_dir / "users" / user_id / "users" / user_id).mkdir(parents=True)
    monkeypatch.setenv("PKB_DATA_DIR", str(data_dir))

    result = runner.invoke(app, ["health"])

    assert result.exit_code == 0, result.output
    assert "status: warning" in result.output
    assert "storage_warning: duplicate_user_roots=1" in result.output
