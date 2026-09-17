"""Cloudflare Access JWT validation for the opt-in V2 Streamlit boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
import ssl
import time
from types import MappingProxyType
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import certifi
import jwt
from jwt import algorithms
from jwt.exceptions import (
    DecodeError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    MissingRequiredClaimError,
)

from pkb.models import IdentityContext, Role

if TYPE_CHECKING:
    from pkb.config import Settings


ACCESS_JWT_HEADER = "Cf-Access-Jwt-Assertion"
SUPPORTED_ALGORITHM = "RS256"
_MAX_TOKEN_LENGTH = 32 * 1024
_MAX_JWKS_BYTES = 1024 * 1024


class AuthError(ValueError):
    """Base error with a stable, safe-to-display failure code and message."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class AuthConfigurationError(AuthError):
    """Raised when V2 authentication cannot be safely configured."""


class AuthenticationError(AuthError):
    """Raised when a request cannot establish a trusted identity."""


RoleValue = Role | str | Sequence[Role | str]
JWKSLoader = Callable[[], Mapping[str, Any]]
Clock = Callable[[], float]


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


def _add_role(
    resolved: dict[str, Role],
    subject: object,
    role_value: object,
) -> None:
    normalized_subject = _text(subject)
    if not normalized_subject:
        raise AuthConfigurationError(
            "invalid_subject_mapping",
            "角色映射中的身份标识不能为空",
        )

    role = _parse_role(role_value)
    previous = resolved.get(normalized_subject)
    if previous is not None and previous is not role:
        raise AuthConfigurationError(
            "conflicting_role",
            "同一身份不能映射到多个角色",
        )
    resolved[normalized_subject] = role


def parse_role_mapping(value: str | Mapping[str, RoleValue]) -> dict[str, Role]:
    """Parse a strict ``sub=role;sub=role`` mapping.

    The string form is used by environment configuration.  A mapping form is
    useful for tests and callers that already parsed a protected configuration.
    Duplicate subjects with different roles fail closed instead of silently
    taking the last value.
    """

    resolved: dict[str, Role] = {}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return resolved
        entries = [entry.strip() for entry in text.replace(",", ";").split(";")]
        for entry in entries:
            if not entry:
                continue
            subject, separator, role = entry.partition("=")
            if not separator or "=" in role:
                raise AuthConfigurationError(
                    "invalid_role_mapping",
                    "角色映射格式应为 sub=admin 或 sub=member",
                )
            _add_role(resolved, subject, role)
        return resolved

    if not isinstance(value, Mapping):
        raise AuthConfigurationError("invalid_role_mapping", "角色映射格式无效")

    for subject, role_value in value.items():
        if isinstance(role_value, Sequence) and not isinstance(role_value, str):
            roles = list(role_value)
            if not roles:
                raise AuthConfigurationError(
                    "conflicting_role",
                    "同一身份必须恰好映射一个角色",
                )
            parsed_roles = {_parse_role(role) for role in roles}
            if len(parsed_roles) != 1:
                raise AuthConfigurationError(
                    "conflicting_role",
                    "同一身份不能映射到多个角色",
                )
            _add_role(resolved, subject, next(iter(parsed_roles)))
        else:
            _add_role(resolved, subject, role_value)
    return resolved


def _validate_https_url(value: object, *, field_name: str) -> str:
    candidate = _text(value)
    try:
        parsed = urlparse(candidate)
        hostname = parsed.hostname
    except ValueError as exc:
        raise AuthConfigurationError(
            "invalid_auth_config",
            f"{field_name} 必须是无查询参数的 HTTPS 地址",
        ) from exc
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise AuthConfigurationError(
            "invalid_auth_config",
            f"{field_name} 必须是无查询参数的 HTTPS 地址",
        )
    return candidate


@dataclass(frozen=True, slots=True)
class CloudflareAccessConfig:
    """The non-secret values required to validate one Access application."""

    issuer: str
    audience: str
    role_mapping: str | Mapping[str, RoleValue]
    jwks_url: str | None = None
    leeway_seconds: int = 0

    def __post_init__(self) -> None:
        issuer = _validate_https_url(self.issuer, field_name="issuer")
        audience = _text(self.audience)
        if not audience:
            raise AuthConfigurationError("invalid_auth_config", "audience 不能为空")
        expected_jwks_url = issuer.rstrip("/") + "/cdn-cgi/access/certs"
        configured_jwks_url = _text(self.jwks_url)
        if configured_jwks_url:
            jwks_url = _validate_https_url(
                configured_jwks_url,
                field_name="jwks_url",
            )
            if jwks_url != expected_jwks_url:
                raise AuthConfigurationError(
                    "invalid_auth_config",
                    "jwks_url 必须是 issuer 对应的 Cloudflare Access 证书端点",
                )
        else:
            jwks_url = expected_jwks_url
        if isinstance(self.leeway_seconds, bool) or not isinstance(
            self.leeway_seconds, int
        ) or self.leeway_seconds < 0:
            raise AuthConfigurationError(
                "invalid_auth_config",
                "认证时间容差必须是非负整数",
            )
        role_mapping = parse_role_mapping(self.role_mapping)
        if not role_mapping:
            raise AuthConfigurationError(
                "missing_role_mapping",
                "V2 认证必须配置身份角色映射",
            )

        object.__setattr__(self, "issuer", issuer)
        object.__setattr__(self, "audience", audience)
        object.__setattr__(self, "jwks_url", jwks_url)
        object.__setattr__(self, "role_mapping", MappingProxyType(role_mapping))

    @classmethod
    def from_settings(cls, settings: Settings) -> "CloudflareAccessConfig":
        """Build a validated config without reading any request-provided data."""

        values = {
            "issuer": settings.auth_issuer,
            "audience": settings.auth_audience,
            "jwks_url": settings.auth_jwks_url,
            "role_mapping": settings.auth_role_mapping,
        }
        if not all(_text(values[key]) for key in ("issuer", "audience")):
            raise AuthConfigurationError(
                "incomplete_auth_config",
                "V2 认证配置不完整，请检查 issuer 和 audience",
            )
        return cls(
            issuer=values["issuer"],
            audience=values["audience"],
            jwks_url=values["jwks_url"],
            role_mapping=values["role_mapping"] or "",
        )


def _fetch_jwks(url: str) -> Mapping[str, Any]:
    """Fetch the configured official certificate set over verified HTTPS."""

    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    with urlopen(request, timeout=5, context=ssl_context) as response:
        payload = response.read(_MAX_JWKS_BYTES + 1)
    if len(payload) > _MAX_JWKS_BYTES:
        raise ValueError("JWKS response too large")
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, Mapping):
        raise ValueError("JWKS response is not an object")
    return decoded


def _jwks_loader(url: str) -> JWKSLoader:
    return lambda: _fetch_jwks(url)


def _unverified_header(token: str) -> Mapping[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except (DecodeError, InvalidTokenError) as exc:
        raise AuthenticationError("invalid_token", "身份令牌格式无效") from exc
    if not isinstance(header, Mapping):
        raise AuthenticationError("invalid_token", "身份令牌格式无效")
    if header.get("alg") != SUPPORTED_ALGORITHM:
        raise AuthenticationError("invalid_algorithm", "身份令牌算法不受支持")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid.strip():
        raise AuthenticationError("missing_key_id", "身份令牌缺少签名密钥标识")
    return header


def _signing_key(
    header: Mapping[str, Any],
    jwks_loader: JWKSLoader,
) -> Any:
    try:
        jwks = jwks_loader()
    except Exception as exc:
        raise AuthenticationError(
            "jwks_unavailable",
            "认证公钥暂不可用，请稍后重试",
        ) from exc

    keys = jwks.get("keys") if isinstance(jwks, Mapping) else None
    if not isinstance(keys, list):
        raise AuthenticationError("invalid_jwks", "认证公钥格式无效")

    kid = header["kid"]
    matches = [
        key
        for key in keys
        if isinstance(key, Mapping) and key.get("kid") == kid
    ]
    if len(matches) != 1:
        raise AuthenticationError("signing_key_not_found", "找不到身份令牌的签名密钥")

    jwk = matches[0]
    key_ops = jwk.get("key_ops")
    if (
        jwk.get("kty") != "RSA"
        or jwk.get("alg") not in (None, SUPPORTED_ALGORITHM)
        or jwk.get("use") not in (None, "sig")
        or key_ops is not None
        and (not isinstance(key_ops, list) or "verify" not in key_ops)
    ):
        raise AuthenticationError("invalid_jwk", "认证公钥算法不受支持")
    try:
        return algorithms.RSAAlgorithm.from_jwk(json.dumps(dict(jwk)))
    except Exception as exc:
        raise AuthenticationError("invalid_jwk", "认证公钥格式无效") from exc


def _required_number(payload: Mapping[str, Any], claim: str) -> float:
    value = payload.get(claim)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuthenticationError("invalid_time_claim", f"身份令牌的 {claim} 无效")
    number = float(value)
    if not math.isfinite(number):
        raise AuthenticationError("invalid_time_claim", f"身份令牌的 {claim} 无效")
    return number


def _claim_text(payload: Mapping[str, Any], claim: str, *, max_length: int = 320) -> str:
    value = _text(payload.get(claim))
    return value[:max_length] if value else ""


def extract_access_token(headers: Mapping[str, Any]) -> str:
    """Read exactly one Access assertion and never inspect the auth cookie."""

    if headers is None:
        raise AuthenticationError("missing_token", "缺少 Cloudflare Access 身份令牌")

    values: list[Any] = []
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        try:
            repeated = get_all(key=ACCESS_JWT_HEADER)
        except TypeError:
            repeated = get_all(ACCESS_JWT_HEADER)
        if repeated:
            values.extend(repeated if isinstance(repeated, (list, tuple)) else [repeated])
    else:
        for key in (
            ACCESS_JWT_HEADER,
            ACCESS_JWT_HEADER.lower(),
            ACCESS_JWT_HEADER.upper(),
        ):
            try:
                candidate = headers.get(key)
            except (AttributeError, TypeError):
                candidate = None
            if candidate is not None:
                values.append(candidate)

    if len(values) != 1 or not isinstance(values[0], str) or not values[0].strip():
        code = "duplicate_token" if len(values) > 1 else "missing_token"
        message = (
            "身份令牌请求头重复"
            if code == "duplicate_token"
            else "缺少 Cloudflare Access 身份令牌"
        )
        raise AuthenticationError(code, message)
    return values[0].strip()


class CloudflareAccessAuthenticator:
    """Verify Cloudflare Access assertions and return a trusted identity."""

    def __init__(
        self,
        config: CloudflareAccessConfig,
        *,
        jwks_loader: JWKSLoader | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.config = config
        self._jwks_loader = jwks_loader or _jwks_loader(config.jwks_url)
        self._clock = clock or time.time

    @classmethod
    def from_settings(cls, settings: Settings) -> "CloudflareAccessAuthenticator":
        return cls(CloudflareAccessConfig.from_settings(settings))

    def authenticate_headers(self, headers: Mapping[str, Any]) -> IdentityContext:
        """Authenticate a read-only Streamlit header mapping."""

        return self.authenticate(extract_access_token(headers))

    def authenticate(self, token: str) -> IdentityContext:
        """Verify one raw JWT without logging or retaining the token."""

        if not isinstance(token, str) or not token.strip():
            raise AuthenticationError("missing_token", "缺少 Cloudflare Access 身份令牌")
        token = token.strip()
        if len(token) > _MAX_TOKEN_LENGTH:
            raise AuthenticationError("invalid_token", "身份令牌格式无效")

        header = _unverified_header(token)
        key = _signing_key(header, self._jwks_loader)
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=[SUPPORTED_ALGORITHM],
                issuer=self.config.issuer,
                audience=self.config.audience,
                options={
                    "require": ["iss", "aud", "exp", "sub"],
                    "verify_signature": True,
                    "verify_exp": False,
                    "verify_nbf": False,
                },
            )
        except InvalidSignatureError as exc:
            raise AuthenticationError("invalid_signature", "身份令牌签名无效") from exc
        except InvalidIssuerError as exc:
            raise AuthenticationError("invalid_issuer", "身份令牌 issuer 不匹配") from exc
        except InvalidAudienceError as exc:
            raise AuthenticationError("invalid_audience", "身份令牌 audience 不匹配") from exc
        except MissingRequiredClaimError as exc:
            claim = _text(getattr(exc, "claim", ""))
            code = {
                "exp": "missing_exp",
                "sub": "missing_sub",
                "iss": "missing_issuer",
                "aud": "missing_audience",
            }.get(claim, "missing_claim")
            raise AuthenticationError(code, f"身份令牌缺少必要字段：{claim or 'claim'}") from exc
        except (InvalidTokenError, TypeError, ValueError) as exc:
            raise AuthenticationError("invalid_token", "身份令牌校验失败") from exc

        if not isinstance(payload, Mapping):
            raise AuthenticationError("invalid_token", "身份令牌载荷格式无效")

        now = float(self._clock())
        exp = _required_number(payload, "exp")
        if exp <= now - self.config.leeway_seconds:
            raise AuthenticationError("expired_token", "身份令牌已过期")
        if "nbf" in payload:
            nbf = _required_number(payload, "nbf")
            if nbf > now + self.config.leeway_seconds:
                raise AuthenticationError("not_yet_valid", "身份令牌尚未生效")

        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject.strip() or len(subject) > 1024:
            raise AuthenticationError("invalid_sub", "身份令牌 sub 无效")
        subject = subject.strip()
        role = self.config.role_mapping.get(subject)
        if role is None:
            raise AuthenticationError("unknown_role", "当前身份未配置可用角色")

        email = _claim_text(payload, "email") or None
        display_name = (
            _claim_text(payload, "name")
            or _claim_text(payload, "preferred_username")
            or email
            or "已认证用户"
        )
        user_id = "u_" + hashlib.sha256(
            f"{self.config.issuer}\0{subject}".encode("utf-8")
        ).hexdigest()
        return IdentityContext(
            user_id=user_id,
            role=role,
            display_name=display_name,
            email=email,
            issuer=self.config.issuer,
            subject=subject,
        )
