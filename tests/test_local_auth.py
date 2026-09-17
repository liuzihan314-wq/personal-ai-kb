from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pkb.auth import (
    AuthConfigurationError,
    AuthenticationError,
    LocalAuthConfig,
    LocalAuthenticator,
    derive_local_user_id,
    hash_password,
    parse_local_users,
    update_local_users_file,
    verify_password,
)
from pkb.models import Role
from pkb.cli.main import app
from pkb.config import get_settings
from typer.testing import CliRunner


runner = CliRunner()


def _hash(password: str) -> str:
    return hash_password(password, iterations=1000)


def test_password_hash_round_trip():
    encoded = _hash("correct horse battery staple")
    assert encoded.startswith("pbkdf2_sha256$1000$")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_short_password_is_rejected():
    with pytest.raises(AuthConfigurationError) as excinfo:
        hash_password("short", iterations=1000)
    assert excinfo.value.code == "weak_password"


def test_parse_local_users_validates_and_maps_roles():
    payload = json.dumps({
        "alice": {
            "password_hash": _hash("alice-password"),
            "role": "admin",
            "display_name": "Alice",
        },
        "bob": {
            "password_hash": _hash("bob-password"),
            "role": "member",
        },
    })
    config = LocalAuthConfig(parse_local_users(payload))
    assert set(config.users) == {"alice", "bob"}
    assert config.users["alice"].role is Role.ADMIN
    assert config.users["bob"].display_name is None


def test_parse_local_users_rejects_case_insensitive_duplicates():
    payload = {
        "alice": {"password_hash": _hash("alice-password"), "role": "member"},
        "ALICE": {"password_hash": _hash("alice-password"), "role": "admin"},
    }
    with pytest.raises(AuthConfigurationError) as excinfo:
        parse_local_users(payload)
    assert excinfo.value.code == "duplicate_user"


def test_local_authenticator_returns_scoped_identity():
    config = LocalAuthConfig(parse_local_users({
        "alice": {
            "password_hash": _hash("alice-password"),
            "role": "admin",
            "display_name": "Alice",
        },
        "bob": {
            "password_hash": _hash("bob-password"),
            "role": "member",
        },
    }))
    authenticator = LocalAuthenticator(config)
    alice = authenticator.authenticate_credentials("alice", "alice-password")
    bob = authenticator.authenticate_credentials("bob", "bob-password")

    assert alice.user_id == derive_local_user_id("alice")
    assert alice.user_id != bob.user_id
    assert re.fullmatch(r"u_[0-9a-f]{64}", alice.user_id)
    assert alice.issuer == "local"
    assert alice.subject == "alice"
    assert alice.role is Role.ADMIN
    assert alice.display_name == "Alice"


def test_local_authenticator_rejects_wrong_password_with_same_code():
    config = LocalAuthConfig(parse_local_users({
        "alice": {
            "password_hash": _hash("alice-password"),
            "role": "member",
        },
    }))
    authenticator = LocalAuthenticator(config)

    with pytest.raises(AuthenticationError) as wrong:
        authenticator.authenticate_credentials("alice", "wrong-password")
    with pytest.raises(AuthenticationError) as unknown:
        authenticator.authenticate_credentials("nobody", "whatever-password")

    assert wrong.value.code == "invalid_credentials"
    assert unknown.value.code == "invalid_credentials"


def test_update_local_users_file_preserves_existing_users(tmp_path: Path):
    path = tmp_path / "config" / "local_users.json"
    update_local_users_file(
        path,
        username="alice",
        password_hash=_hash("alice-password"),
        role="admin",
        display_name="Alice",
    )
    update_local_users_file(
        path,
        username="bob",
        password_hash=_hash("bob-password"),
        role="member",
    )

    assert path.stat().st_mode & 0o777 == 0o600
    config = LocalAuthConfig.from_file(path)
    assert set(config.users) == {"alice", "bob"}
    assert config.users["alice"].role is Role.ADMIN
    assert config.users["bob"].role is Role.MEMBER


def test_auth_hash_password_command_outputs_hash():
    result = runner.invoke(
        app,
        ["auth-hash-password", "--password", "correct horse battery staple"],
    )
    assert result.exit_code == 0, result.output
    assert result.output.startswith("pbkdf2_sha256$600000$")


def test_auth_add_local_user_command_writes_hashed_file(tmp_path: Path, monkeypatch):
    users_file = tmp_path / "local_users.json"
    monkeypatch.setenv("PKB_AUTH_ENABLED", "true")
    monkeypatch.setenv("PKB_AUTH_MODE", "local")
    monkeypatch.setenv("PKB_AUTH_LOCAL_USERS_FILE", str(users_file))
    get_settings.cache_clear()

    result = runner.invoke(
        app,
        [
            "auth-add-local-user",
            "alice",
            "--password",
            "alice-password",
            "--role",
            "member",
            "--display-name",
            "Alice",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "status: saved" in result.output
    config = LocalAuthConfig.from_file(users_file)
    assert config.users["alice"].role is Role.MEMBER
    assert config.users["alice"].display_name == "Alice"


def test_update_local_users_file_rejects_duplicate_username(tmp_path: Path):
    path = tmp_path / "local_users.json"
    update_local_users_file(
        path,
        username="alice",
        password_hash=_hash("alice-password"),
        role="member",
    )
    with pytest.raises(AuthConfigurationError) as excinfo:
        update_local_users_file(
            path,
            username="alice",
            password_hash=_hash("other-password"),
            role="admin",
        )
    assert excinfo.value.code == "duplicate_user"
