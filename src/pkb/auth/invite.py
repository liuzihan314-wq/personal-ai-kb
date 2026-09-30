"""Reusable, revocable invitation codes for isolated public visitors."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import MappingProxyType
from typing import Any, Callable

from pkb.auth.cloudflare import AuthConfigurationError, AuthenticationError
from pkb.auth.local import hash_password, is_valid_password_hash, verify_password
from pkb.models import IdentityContext, Role


_INVITE_ID_PATTERN = re.compile(r"^i_[0-9a-f]{16}$")
_INVITE_CODE_PATTERN = re.compile(r"^pkb_(i_[0-9a-f]{16})_([A-Za-z0-9_-]{32})$")
_DISPLAY_NAME_MAX_LENGTH = 128
_FILE_VERSION = 1


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    resolved = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return resolved.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _display_name(value: object) -> str:
    if not isinstance(value, str):
        raise AuthConfigurationError("invalid_invite_name", "邀请码名称不能为空")
    name = value.strip()
    if not name or len(name) > _DISPLAY_NAME_MAX_LENGTH or any(ord(c) < 32 for c in name):
        raise AuthConfigurationError("invalid_invite_name", "邀请码名称格式无效")
    return name


def _required_text(value: object, *, code: str, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthConfigurationError(code, message)
    return value.strip()


@dataclass(frozen=True, slots=True)
class InvitationRecord:
    """One stored invitation. The reusable plaintext code is never persisted."""

    invite_id: str
    code_hash: str
    display_name: str
    active: bool
    created_at: str
    revoked_at: str | None = None

    def __post_init__(self) -> None:
        if not _INVITE_ID_PATTERN.fullmatch(self.invite_id):
            raise AuthConfigurationError("invalid_invite_id", "邀请码记录 ID 格式无效")
        object.__setattr__(self, "display_name", _display_name(self.display_name))
        if not isinstance(self.active, bool):
            raise AuthConfigurationError("invalid_invite_record", "邀请码状态格式无效")
        _required_text(
            self.created_at,
            code="invalid_invite_record",
            message="邀请码创建时间格式无效",
        )
        if self.revoked_at is not None:
            _required_text(
                self.revoked_at,
                code="invalid_invite_record",
                message="邀请码撤销时间格式无效",
            )
        if not is_valid_password_hash(self.code_hash):
            raise AuthConfigurationError("invalid_invite_hash", "邀请码哈希格式无效")


@dataclass(frozen=True, slots=True)
class InvitationConfig:
    """Parsed invitation configuration with stable record ordering."""

    invitations: Mapping[str, InvitationRecord]

    def __post_init__(self) -> None:
        object.__setattr__(self, "invitations", MappingProxyType(dict(self.invitations)))

    @classmethod
    def from_file(cls, path: str | Path) -> "InvitationConfig":
        return cls(parse_invitations(_read_payload(Path(path), allow_missing=False)))


@dataclass(frozen=True, slots=True)
class CreatedInvitation:
    """A newly generated credential whose code is returned exactly once."""

    record: InvitationRecord
    code: str


def _read_payload(path: Path, *, allow_missing: bool) -> Mapping[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        if allow_missing:
            return {"version": _FILE_VERSION, "invitations": {}}
        raise AuthConfigurationError(
            "missing_invites_file",
            f"邀请码配置文件不存在：{path.name}",
        ) from exc
    except OSError as exc:
        raise AuthConfigurationError("invites_file_unavailable", "邀请码配置文件不可读") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AuthConfigurationError("invalid_invites_json", "邀请码配置 JSON 格式无效") from exc
    if not isinstance(payload, Mapping):
        raise AuthConfigurationError("invalid_invites_json", "邀请码配置必须是 JSON 对象")
    return payload


def parse_invitations(payload: Mapping[str, Any]) -> dict[str, InvitationRecord]:
    """Validate a versioned invitation file without exposing stored hashes."""

    if payload.get("version") != _FILE_VERSION:
        raise AuthConfigurationError("invalid_invites_version", "邀请码配置版本不受支持")
    raw_invitations = payload.get("invitations")
    if not isinstance(raw_invitations, Mapping):
        raise AuthConfigurationError("invalid_invites_json", "邀请码记录必须是 JSON 对象")

    records: dict[str, InvitationRecord] = {}
    for invite_id, raw in raw_invitations.items():
        if not isinstance(invite_id, str) or not isinstance(raw, Mapping):
            raise AuthConfigurationError("invalid_invite_record", "邀请码记录格式无效")
        record = InvitationRecord(
            invite_id=invite_id,
            code_hash=_required_text(
                raw.get("code_hash"),
                code="invalid_invite_hash",
                message="邀请码哈希格式无效",
            ),
            display_name=raw.get("display_name"),
            active=raw.get("active"),
            created_at=raw.get("created_at"),
            revoked_at=raw.get("revoked_at"),
        )
        records[invite_id] = record
    return records


def _payload(records: Mapping[str, InvitationRecord]) -> dict[str, Any]:
    return {
        "version": _FILE_VERSION,
        "invitations": {
            invite_id: {
                "code_hash": record.code_hash,
                "display_name": record.display_name,
                "active": record.active,
                "created_at": record.created_at,
                "revoked_at": record.revoked_at,
            }
            for invite_id, record in sorted(records.items())
        },
    }


def _write_records(path: Path, records: Mapping[str, InvitationRecord]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_payload(records), ensure_ascii=False, indent=2) + "\n"
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".invites.",
        delete=False,
    ) as temporary:
        temporary.write(text)
        temporary_path = Path(temporary.name)
    os.chmod(temporary_path, 0o600)
    temporary_path.replace(path)
    return path


def create_invitation(
    path: str | Path,
    *,
    display_name: str,
    clock: Callable[[], datetime] = _utc_now,
    iterations: int = 600_000,
) -> CreatedInvitation:
    """Create one reusable invitation and return its plaintext code once."""

    config_path = Path(path)
    records = parse_invitations(_read_payload(config_path, allow_missing=True))
    name = _display_name(display_name)
    while True:
        invite_id = "i_" + secrets.token_hex(8)
        if invite_id not in records:
            break
    code = f"pkb_{invite_id}_{secrets.token_urlsafe(24)}"
    record = InvitationRecord(
        invite_id=invite_id,
        code_hash=hash_password(code, iterations=iterations),
        display_name=name,
        active=True,
        created_at=_timestamp(clock()),
    )
    records[invite_id] = record
    _write_records(config_path, records)
    return CreatedInvitation(record=record, code=code)


def list_invitations(path: str | Path) -> tuple[InvitationRecord, ...]:
    """Return configured invitations without plaintext credentials."""

    config_path = Path(path)
    records = parse_invitations(_read_payload(config_path, allow_missing=True))
    return tuple(records[invite_id] for invite_id in sorted(records))


def revoke_invitation(
    path: str | Path,
    invite_id: str,
    *,
    clock: Callable[[], datetime] = _utc_now,
) -> bool:
    """Revoke one invitation. Return false when it was already inactive."""

    if not isinstance(invite_id, str) or not _INVITE_ID_PATTERN.fullmatch(invite_id):
        raise AuthConfigurationError("invalid_invite_id", "邀请码记录 ID 格式无效")
    config_path = Path(path)
    records = parse_invitations(_read_payload(config_path, allow_missing=False))
    current = records.get(invite_id)
    if current is None:
        raise AuthConfigurationError("unknown_invite", "邀请码记录不存在")
    if not current.active:
        return False
    records[invite_id] = InvitationRecord(
        invite_id=current.invite_id,
        code_hash=current.code_hash,
        display_name=current.display_name,
        active=False,
        created_at=current.created_at,
        revoked_at=_timestamp(clock()),
    )
    _write_records(config_path, records)
    return True


def derive_invite_user_id(invite_id: str) -> str:
    """Derive the stable isolated storage id for one invitation record."""

    if not isinstance(invite_id, str) or not _INVITE_ID_PATTERN.fullmatch(invite_id):
        raise AuthConfigurationError("invalid_invite_id", "邀请码记录 ID 格式无效")
    return "u_" + hashlib.sha256(f"invite\0{invite_id}".encode("utf-8")).hexdigest()


class InviteAuthenticator:
    """Authenticate one reusable invitation code into an isolated member identity."""

    def __init__(self, config: InvitationConfig) -> None:
        self.config = config

    @classmethod
    def from_settings(cls, settings: Any) -> "InviteAuthenticator":
        return cls(InvitationConfig.from_file(settings.auth_invites_file))

    def authenticate_code(self, code: str) -> IdentityContext:
        if not isinstance(code, str):
            raise AuthenticationError("invalid_invite", "邀请码无效或已撤销")
        match = _INVITE_CODE_PATTERN.fullmatch(code.strip())
        if match is None:
            raise AuthenticationError("invalid_invite", "邀请码无效或已撤销")
        invite_id = match.group(1)
        record = self.config.invitations.get(invite_id)
        if record is None or not record.active or not verify_password(code.strip(), record.code_hash):
            raise AuthenticationError("invalid_invite", "邀请码无效或已撤销")
        return IdentityContext(
            user_id=derive_invite_user_id(invite_id),
            role=Role.MEMBER,
            display_name=record.display_name,
            issuer="invite",
            subject=invite_id,
        )

    def is_identity_active(self, identity: IdentityContext) -> bool:
        """Revalidate an existing browser session after possible revocation."""

        if identity.issuer != "invite" or not _INVITE_ID_PATTERN.fullmatch(identity.subject):
            return False
        record = self.config.invitations.get(identity.subject)
        return bool(
            record is not None
            and record.active
            and identity.user_id == derive_invite_user_id(identity.subject)
        )


__all__ = [
    "CreatedInvitation",
    "InvitationConfig",
    "InvitationRecord",
    "InviteAuthenticator",
    "create_invitation",
    "derive_invite_user_id",
    "list_invitations",
    "parse_invitations",
    "revoke_invitation",
]
