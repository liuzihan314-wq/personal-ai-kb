"""Local username/password authentication for the no-domain V2 share mode."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import MappingProxyType
from typing import Any

from pkb.auth.cloudflare import AuthConfigurationError, AuthenticationError
from pkb.models import IdentityContext, Role

_PASSWORD_SCHEME = "pbkdf2_sha256"
_DEFAULT_ITERATIONS = 600_000
_MIN_PASSWORD_LENGTH = 8
_MAX_PASSWORD_LENGTH = 1024
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_DISPLAY_NAME_MAX_LENGTH = 128


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_role(value: object) -> Role:
    candidate = _text(value).lower()
    try:
        return Role(candidate)
    except ValueError as exc:
        raise AuthConfigurationError(
            "unknown_role",
            "角色配置只能使用 admin 或 member",
        ) from exc


def hash_password(password: str, *, iterations: int = _DEFAULT_ITERATIONS) -> str:
    """Return a salted PBKDF2-SHA256 hash for one local account password."""

    if not isinstance(password, str) or len(password) < _MIN_PASSWORD_LENGTH:
        raise AuthConfigurationError("weak_password", "本地账号密码至少需要 8 个字符")
    if len(password) > _MAX_PASSWORD_LENGTH:
        raise AuthConfigurationError("invalid_password", "本地账号密码过长")
    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 1000:
        raise AuthConfigurationError("invalid_password_hash", "密码哈希迭代次数无效")

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{_PASSWORD_SCHEME}${iterations}${salt_text}${digest_text}"


def _split_password_hash(encoded: str) -> tuple[int, bytes, bytes]:
    if not isinstance(encoded, str):
        raise ValueError
    parts = encoded.split("$")
    if len(parts) != 4 or parts[0] != _PASSWORD_SCHEME:
        raise ValueError
    try:
        iterations = int(parts[1])
    except ValueError as exc:
        raise ValueError from exc
    if iterations < 1000 or iterations > 10_000_000:
        raise ValueError
    try:
        salt = base64.urlsafe_b64decode(parts[2] + "=" * (-len(parts[2]) % 4))
        digest = base64.urlsafe_b64decode(parts[3] + "=" * (-len(parts[3]) % 4))
    except Exception as exc:
        raise ValueError from exc
    if len(salt) != 16 or len(digest) != 32:
        raise ValueError
    return iterations, salt, digest


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password against a stored hash without logging either value."""

    if not isinstance(password, str):
        return False
    try:
        iterations, salt, expected = _split_password_hash(encoded)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


@dataclass(frozen=True, slots=True)
class LocalUserRecord:
    """One configured local account, containing only a password hash."""

    username: str
    password_hash: str
    role: Role
    display_name: str | None = None

    def __post_init__(self) -> None:
        if not _USERNAME_PATTERN.fullmatch(self.username):
            raise AuthConfigurationError(
                "invalid_username",
                "本地用户名只能包含字母、数字、点、下划线和连字符",
            )
        if self.display_name is not None:
            if not isinstance(self.display_name, str):
                raise AuthConfigurationError("invalid_display_name", "显示名格式无效")
            name = _text(self.display_name)
            if not name or len(name) > _DISPLAY_NAME_MAX_LENGTH or any(ord(c) < 32 for c in name):
                raise AuthConfigurationError("invalid_display_name", "显示名格式无效")
            object.__setattr__(self, "display_name", name)
        try:
            _split_password_hash(self.password_hash)
        except ValueError as exc:
            raise AuthConfigurationError("invalid_password_hash", "密码哈希格式无效") from exc


@dataclass(frozen=True, slots=True)
class LocalAuthConfig:
    """Parsed local account configuration with an immutable user mapping."""

    users: Mapping[str, LocalUserRecord]

    def __post_init__(self) -> None:
        if not self.users:
            raise AuthConfigurationError("empty_local_users", "本地账号配置不能为空")
        object.__setattr__(self, "users", MappingProxyType(dict(self.users)))

    @classmethod
    def from_file(cls, path: str | Path) -> "LocalAuthConfig":
        config_path = Path(path)
        try:
            text = config_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise AuthConfigurationError(
                "missing_local_users_file",
                f"本地账号配置文件不存在：{config_path.name}",
            ) from exc
        except OSError as exc:
            raise AuthConfigurationError(
                "local_users_file_unavailable",
                "本地账号配置文件不可读",
            ) from exc
        return cls(parse_local_users(text))


def parse_local_users(value: str | Mapping[str, Any]) -> dict[str, LocalUserRecord]:
    """Parse a JSON string or mapping of local accounts."""

    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise AuthConfigurationError("empty_local_users", "本地账号配置不能为空")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AuthConfigurationError("invalid_local_users_json", "本地账号配置 JSON 格式无效") from exc
    elif isinstance(value, Mapping):
        payload = value
    else:
        raise AuthConfigurationError("invalid_local_users_json", "本地账号配置格式无效")

    if not isinstance(payload, Mapping):
        raise AuthConfigurationError("invalid_local_users_json", "本地账号配置必须是 JSON 对象")

    resolved: dict[str, LocalUserRecord] = {}
    for username, raw in payload.items():
        if not isinstance(username, str) or not _USERNAME_PATTERN.fullmatch(username):
            raise AuthConfigurationError(
                "invalid_username",
                "本地用户名只能包含字母、数字、点、下划线和连字符",
            )
        folded = username.casefold()
        if any(existing.casefold() == folded for existing in resolved):
            raise AuthConfigurationError("duplicate_user", "本地用户名不能重复")
        if not isinstance(raw, Mapping):
            raise AuthConfigurationError("invalid_user_record", "本地用户配置必须是对象")

        resolved[username] = LocalUserRecord(
            username=username,
            password_hash=_text(raw.get("password_hash")),
            role=_parse_role(raw.get("role")),
            display_name=raw.get("display_name"),
        )
    return resolved


def update_local_users_file(
    path: str | Path,
    *,
    username: str,
    password_hash: str,
    role: str | Role,
    display_name: str | None = None,
) -> Path:
    """Add one local user to an atomic, mode-600 JSON file."""

    config_path = Path(path)
    existing: dict[str, Any] = {}
    if config_path.exists():
        config = LocalAuthConfig.from_file(config_path)
        existing = {
            record.username: {
                "password_hash": record.password_hash,
                "role": record.role.value,
                "display_name": record.display_name,
            }
            for record in config.users.values()
        }

    record = LocalUserRecord(
        username=username,
        password_hash=password_hash,
        role=_parse_role(role),
        display_name=display_name,
    )
    folded = record.username.casefold()
    if any(name.casefold() == folded for name in existing):
        raise AuthConfigurationError("duplicate_user", "本地用户名已存在")

    existing[record.username] = {
        "password_hash": record.password_hash,
        "role": record.role.value,
        "display_name": record.display_name,
    }
    payload = json.dumps(existing, ensure_ascii=False, indent=2) + "\n"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=config_path.parent,
        prefix=".local_users.",
        delete=False,
    ) as temporary:
        temporary.write(payload)
        temporary_path = Path(temporary.name)
    os.chmod(temporary_path, 0o600)
    temporary_path.replace(config_path)
    return config_path


class LocalAuthenticator:
    """Authenticate local username/password credentials into a trusted identity."""

    def __init__(self, config: LocalAuthConfig) -> None:
        self.config = config

    @classmethod
    def from_settings(cls, settings: Any) -> "LocalAuthenticator":
        return cls(LocalAuthConfig.from_file(settings.auth_local_users_file))

    def authenticate_credentials(self, username: str, password: str) -> IdentityContext:
        if not isinstance(username, str) or not _USERNAME_PATTERN.fullmatch(username):
            raise AuthenticationError("invalid_credentials", "用户名或密码错误")
        if not isinstance(password, str):
            raise AuthenticationError("invalid_credentials", "用户名或密码错误")

        record = self.config.users.get(username)
        if record is None:
            raise AuthenticationError("invalid_credentials", "用户名或密码错误")
        if not verify_password(password, record.password_hash):
            raise AuthenticationError("invalid_credentials", "用户名或密码错误")

        return IdentityContext(
            user_id=derive_local_user_id(username),
            role=record.role,
            display_name=record.display_name or username,
            issuer="local",
            subject=username,
        )


def derive_local_user_id(username: str) -> str:
    """Derive a path-safe internal id for a local account username."""

    return "u_" + hashlib.sha256(f"local\0{username}".encode("utf-8")).hexdigest()
