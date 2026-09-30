from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pkb.auth import (
    AuthenticationError,
    InvitationConfig,
    InviteAuthenticator,
    create_invitation,
    derive_invite_user_id,
    list_invitations,
    revoke_invitation,
)
from pkb.cli.main import app
from pkb.config import Settings, get_settings
from pkb.providers import MockAIProvider
from pkb.ui import UIService


FIXED_TIME = datetime(2026, 9, 27, 3, 0, tzinfo=timezone.utc)
runner = CliRunner()


def _create(path: Path, name: str, *, api_mode: str = "shared"):
    return create_invitation(
        path,
        display_name=name,
        api_mode=api_mode,
        clock=lambda: FIXED_TIME,
        iterations=1000,
    )


def test_invitation_round_trip_stores_only_hash_and_stable_identity(tmp_path: Path):
    path = tmp_path / "config" / "invites.json"
    created = _create(path, "访客甲")

    assert path.stat().st_mode & 0o777 == 0o600
    assert created.code.startswith(f"pkb_{created.record.invite_id}_")
    assert created.code not in path.read_text(encoding="utf-8")
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = payload["invitations"][created.record.invite_id]
    assert stored["code_hash"].startswith("pbkdf2_sha256$")

    authenticator = InviteAuthenticator(InvitationConfig.from_file(path))
    identity = authenticator.authenticate_code(created.code)
    assert identity.user_id == derive_invite_user_id(created.record.invite_id)
    assert re.fullmatch(r"u_[0-9a-f]{64}", identity.user_id)
    assert identity.display_name == "访客甲"
    assert identity.issuer == "invite"
    assert authenticator.is_identity_active(identity)
    assert authenticator.api_mode_for_identity(identity) == "shared"


def test_invitation_api_modes_are_persisted_and_legacy_records_default_to_shared(
    tmp_path: Path,
):
    path = tmp_path / "config" / "invites.json"
    byok = _create(path, "自带 API 访客", api_mode="byok")
    shared = _create(path, "共用主人 API")
    records = {record.invite_id: record for record in list_invitations(path)}

    assert records[byok.record.invite_id].api_mode == "byok"
    assert records[shared.record.invite_id].api_mode == "shared"

    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["invitations"][shared.record.invite_id]["api_mode"]
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(json.dumps(payload), encoding="utf-8")
    legacy_records = list_invitations(legacy_path)
    legacy_shared = next(
        record for record in legacy_records if record.invite_id == shared.record.invite_id
    )
    assert legacy_shared.api_mode == "shared"

    authenticator = InviteAuthenticator(InvitationConfig.from_file(path))
    byok_identity = authenticator.authenticate_code(byok.code)
    assert authenticator.api_mode_for_identity(byok_identity) == "byok"


def test_different_invitations_are_isolated_and_revocation_fails_closed(
    tmp_path: Path,
    monkeypatch,
):
    path = tmp_path / "config" / "invites.json"
    first = _create(path, "访客甲")
    second = _create(path, "访客乙")
    authenticator = InviteAuthenticator(InvitationConfig.from_file(path))
    first_identity = authenticator.authenticate_code(first.code)
    second_identity = authenticator.authenticate_code(second.code)

    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    monkeypatch.setattr("pkb.ui.services.get_settings", lambda: settings)
    first_service = UIService(identity=first_identity, provider=MockAIProvider())
    second_service = UIService(identity=second_identity, provider=MockAIProvider())
    first_service.add_idea("alphaonlymaterial", tags=["private"])
    second_service.add_idea("betaonlymaterial", tags=["private"])

    assert first_service.paths.raw_dir != second_service.paths.raw_dir
    assert first_service.search("betaonlymaterial").status == "no_hits"
    assert second_service.search("alphaonlymaterial").status == "no_hits"

    assert revoke_invitation(path, first.record.invite_id, clock=lambda: FIXED_TIME)
    assert not revoke_invitation(path, first.record.invite_id, clock=lambda: FIXED_TIME)
    refreshed = InviteAuthenticator(InvitationConfig.from_file(path))
    assert not refreshed.is_identity_active(first_identity)
    with pytest.raises(AuthenticationError) as excinfo:
        refreshed.authenticate_code(first.code)
    assert excinfo.value.code == "invalid_invite"
    assert refreshed.authenticate_code(second.code).user_id == second_identity.user_id


def test_invalid_invitation_uses_one_generic_error(tmp_path: Path):
    path = tmp_path / "invites.json"
    created = _create(path, "访客甲")
    authenticator = InviteAuthenticator(InvitationConfig.from_file(path))

    changed_code = created.code[:-1] + ("A" if created.code[-1] != "A" else "B")
    for candidate in ("", "wrong", changed_code):
        with pytest.raises(AuthenticationError) as excinfo:
            authenticator.authenticate_code(candidate)
        assert excinfo.value.code == "invalid_invite"
        assert "无效或已撤销" in str(excinfo.value)


def test_invite_cli_create_list_and_revoke_without_exposing_hash(
    tmp_path: Path,
    monkeypatch,
):
    path = tmp_path / "config" / "invites.json"
    monkeypatch.setenv("PKB_AUTH_INVITES_FILE", str(path))
    get_settings.cache_clear()

    created = runner.invoke(app, ["invite-create", "--name", "访客甲"])
    assert created.exit_code == 0, created.output
    assert "status: created" in created.output
    code = next(line.removeprefix("code: ") for line in created.output.splitlines() if line.startswith("code: "))
    invite_id = next(
        line.removeprefix("invite_id: ")
        for line in created.output.splitlines()
        if line.startswith("invite_id: ")
    )
    assert code not in path.read_text(encoding="utf-8")

    listed = runner.invoke(app, ["invite-list"])
    assert listed.exit_code == 0, listed.output
    assert invite_id in listed.output
    assert "访客甲" in listed.output
    assert "shared" in listed.output
    assert "pbkdf2" not in listed.output
    assert code not in listed.output

    revoked = runner.invoke(app, ["invite-revoke", invite_id])
    assert revoked.exit_code == 0, revoked.output
    assert "status: revoked" in revoked.output
    assert list_invitations(path)[0].active is False


def test_invite_cli_can_create_byok_invitation(tmp_path: Path, monkeypatch):
    path = tmp_path / "config" / "invites.json"
    monkeypatch.setenv("PKB_AUTH_INVITES_FILE", str(path))
    get_settings.cache_clear()

    created = runner.invoke(
        app,
        ["invite-create", "--name", "自带 API 访客", "--api-mode", "byok"],
    )

    assert created.exit_code == 0, created.output
    assert "api_mode: byok" in created.output
    assert list_invitations(path)[0].api_mode == "byok"


def test_output_launcher_always_opens_current_source_in_passwordless_owner_mode():
    project_root = Path(__file__).resolve().parents[1]
    launcher = (project_root / "output" / "打开知识库.command").read_text(
        encoding="utf-8"
    )

    assert 'APP_FILE="$PROJECT_DIR/src/pkb/ui/app.py"' in launcher
    assert "export PKB_AUTH_ENABLED=false" in launcher
    assert "--server.address 127.0.0.1" in launcher
    assert "--server.runOnSave true" in launcher
    assert "output/app.py" not in launcher
