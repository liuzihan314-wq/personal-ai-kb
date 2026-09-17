import base64
from datetime import datetime, timezone
import hashlib
import logging
import ssl

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from pkb.auth import (
    ACCESS_JWT_HEADER,
    AuthConfigurationError,
    AuthenticationError,
    CloudflareAccessAuthenticator,
    CloudflareAccessConfig,
    extract_access_token,
    parse_role_mapping,
)
from pkb.models import Role


ISSUER = "https://access.example.test"
AUDIENCE = "synthetic-audience"
JWKS_URL = "https://access.example.test/cdn-cgi/access/certs"
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
KID = "synthetic-key"


def _base64url_number(value: int) -> str:
    size = (value.bit_length() + 7) // 8
    encoded = base64.urlsafe_b64encode(value.to_bytes(size, "big"))
    return encoded.rstrip(b"=").decode("ascii")


@pytest.fixture()
def key_material():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": KID,
                "use": "sig",
                "alg": "RS256",
                "n": _base64url_number(numbers.n),
                "e": _base64url_number(numbers.e),
            }
        ]
    }
    return private_key, jwks


def _config(role_mapping="subject-admin=admin;subject-member=member"):
    return CloudflareAccessConfig(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url=JWKS_URL,
        role_mapping=role_mapping,
    )


def _authenticator(key_material, *, role_mapping=None):
    private_key, jwks = key_material
    return CloudflareAccessAuthenticator(
        _config(role_mapping or "subject-admin=admin;subject-member=member"),
        jwks_loader=lambda: jwks,
        clock=lambda: NOW.timestamp(),
    ), private_key


def _token(private_key, *, omit=(), **claims):
    payload = {
        "iss": ISSUER,
        "aud": [AUDIENCE],
        "exp": int(NOW.timestamp()) + 300,
        "sub": "subject-admin",
        "email": "admin@example.test",
        "name": "Synthetic Admin",
    }
    for claim in omit:
        payload.pop(claim, None)
    payload.update(claims)
    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": KID},
    )


def test_valid_access_jwt_returns_stable_identity_and_admin_role(key_material):
    authenticator, private_key = _authenticator(key_material)
    token = _token(private_key)

    first = authenticator.authenticate(token)
    second = authenticator.authenticate(token)

    assert first == second
    assert first.role is Role.ADMIN
    assert first.is_admin is True
    assert first.display_name == "Synthetic Admin"
    assert first.email == "admin@example.test"
    assert first.user_id == "u_" + hashlib.sha256(
        f"{ISSUER}\0subject-admin".encode("utf-8")
    ).hexdigest()
    assert "admin@example.test" not in first.user_id
    assert first.subject == "subject-admin"


def test_member_role_is_explicitly_distinct_from_admin(key_material):
    authenticator, private_key = _authenticator(key_material)
    identity = authenticator.authenticate(
        _token(
            private_key,
            sub="subject-member",
            email="member@example.test",
            name="Synthetic Member",
        )
    )

    assert identity.role is Role.MEMBER
    assert identity.role.display_name == "成员"
    assert identity.is_admin is False
    assert identity.user_id != "u_" + hashlib.sha256(
        f"{ISSUER}\0subject-admin".encode("utf-8")
    ).hexdigest()


def test_headers_accept_only_one_access_assertion_and_never_cookie(key_material):
    authenticator, private_key = _authenticator(key_material)
    token = _token(private_key)

    assert authenticator.authenticate_headers({ACCESS_JWT_HEADER: token}).role is Role.ADMIN
    assert authenticator.authenticate_headers({ACCESS_JWT_HEADER.lower(): token}).role is Role.ADMIN

    with pytest.raises(AuthenticationError) as missing:
        extract_access_token({"CF_Authorization": token})
    assert missing.value.code == "missing_token"

    class RepeatedHeaders:
        def get_all(self, *, key):
            assert key == ACCESS_JWT_HEADER
            return [token, token]

    with pytest.raises(AuthenticationError) as duplicate:
        extract_access_token(RepeatedHeaders())
    assert duplicate.value.code == "duplicate_token"


@pytest.mark.parametrize(
    ("claims", "expected_code"),
    [
        ({"iss": "https://other.example.test"}, "invalid_issuer"),
        ({"aud": "other-audience"}, "invalid_audience"),
        ({"exp": int(NOW.timestamp()) - 1}, "expired_token"),
        ({"sub": ""}, "invalid_sub"),
        ({"sub": None}, "missing_sub"),
        ({"exp": "not-a-number"}, "invalid_time_claim"),
    ],
)
def test_invalid_claims_fail_closed(key_material, claims, expected_code):
    authenticator, private_key = _authenticator(key_material)
    with pytest.raises(AuthenticationError) as error:
        authenticator.authenticate(_token(private_key, **claims))
    assert error.value.code == expected_code


def test_missing_required_claims_fail_closed(key_material):
    authenticator, private_key = _authenticator(key_material)

    with pytest.raises(AuthenticationError) as exp_error:
        authenticator.authenticate(_token(private_key, omit={"exp"}))
    assert exp_error.value.code == "missing_exp"

    with pytest.raises(AuthenticationError) as sub_error:
        authenticator.authenticate(_token(private_key, omit={"sub"}))
    assert sub_error.value.code == "missing_sub"


def test_invalid_signature_unknown_role_and_unsupported_algorithm_fail_closed(key_material):
    authenticator, private_key = _authenticator(key_material)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(AuthenticationError) as signature_error:
        authenticator.authenticate(_token(other_key))
    assert signature_error.value.code == "invalid_signature"

    with pytest.raises(AuthenticationError) as role_error:
        authenticator.authenticate(_token(private_key, sub="subject-unknown"))
    assert role_error.value.code == "unknown_role"

    unsupported = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": int(NOW.timestamp()) + 300,
            "sub": "subject-admin",
        },
        "synthetic-only-secret-32-bytes-long",
        algorithm="HS256",
        headers={"kid": KID},
    )
    with pytest.raises(AuthenticationError) as algorithm_error:
        authenticator.authenticate(unsupported)
    assert algorithm_error.value.code == "invalid_algorithm"


def test_not_before_is_checked_with_injected_clock(key_material):
    authenticator, private_key = _authenticator(key_material)
    with pytest.raises(AuthenticationError) as error:
        authenticator.authenticate(
            _token(private_key, nbf=int(NOW.timestamp()) + 60)
        )
    assert error.value.code == "not_yet_valid"


def test_role_mapping_rejects_unknown_and_conflicting_roles():
    assert parse_role_mapping("subject-admin=admin;subject-member=member") == {
        "subject-admin": Role.ADMIN,
        "subject-member": Role.MEMBER,
    }

    with pytest.raises(AuthConfigurationError) as unknown:
        parse_role_mapping("subject-admin=owner")
    assert unknown.value.code == "unknown_role"

    with pytest.raises(AuthConfigurationError) as conflict:
        parse_role_mapping("subject-admin=admin;subject-admin=member")
    assert conflict.value.code == "conflicting_role"

    with pytest.raises(AuthConfigurationError) as mapping_conflict:
        CloudflareAccessConfig(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_url=JWKS_URL,
            role_mapping={"subject-admin": ["admin", "member"]},
        )
    assert mapping_conflict.value.code == "conflicting_role"


def test_jwks_endpoint_is_derived_from_and_bound_to_issuer():
    derived = CloudflareAccessConfig(
        issuer=ISSUER,
        audience=AUDIENCE,
        role_mapping="subject-admin=admin",
    )
    assert derived.jwks_url == JWKS_URL

    with pytest.raises(AuthConfigurationError) as mismatch:
        CloudflareAccessConfig(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_url="https://other.example.test/certs",
            role_mapping="subject-admin=admin",
        )
    assert mismatch.value.code == "invalid_auth_config"


def test_jwks_fetch_uses_the_derived_endpoint_without_auth_headers(monkeypatch):
    from pkb.auth import cloudflare as cloudflare_auth

    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit):
            captured["limit"] = limit
            return b'{"keys": []}'

    def fake_urlopen(request, *, timeout, context):
        captured["request"] = request
        captured["timeout"] = timeout
        captured["context"] = context
        return Response()

    monkeypatch.setattr(cloudflare_auth, "urlopen", fake_urlopen)

    assert cloudflare_auth._fetch_jwks(JWKS_URL) == {"keys": []}
    assert captured["request"].full_url == JWKS_URL
    assert captured["request"].headers["Accept"] == "application/json"
    assert "Authorization" not in captured["request"].headers
    assert "Cookie" not in captured["request"].headers
    assert captured["timeout"] == 5
    assert isinstance(captured["context"], ssl.SSLContext)
    assert captured["context"].verify_mode == ssl.CERT_REQUIRED


def test_auth_failures_do_not_log_token_or_cookie(caplog, key_material):
    authenticator, private_key = _authenticator(key_material)
    token = _token(private_key, sub="subject-unknown")
    caplog.set_level(logging.DEBUG)

    with pytest.raises(AuthenticationError):
        authenticator.authenticate(token)

    assert token not in caplog.text
    assert ACCESS_JWT_HEADER not in caplog.text
    assert "CF_Authorization" not in caplog.text
