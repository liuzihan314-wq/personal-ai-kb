"""Authentication adapters for the optional V2 application boundary."""

from pkb.auth.cloudflare import (
    ACCESS_JWT_HEADER,
    SUPPORTED_ALGORITHM,
    AuthConfigurationError,
    AuthError,
    AuthenticationError,
    CloudflareAccessAuthenticator,
    CloudflareAccessConfig,
    extract_access_token,
    parse_role_mapping,
)
from pkb.auth.local import (
    LocalAuthConfig,
    LocalAuthenticator,
    LocalUserRecord,
    derive_local_user_id,
    hash_password,
    parse_local_users,
    update_local_users_file,
    verify_password,
)
from pkb.models import IdentityContext, Role

__all__ = [
    "ACCESS_JWT_HEADER",
    "SUPPORTED_ALGORITHM",
    "AuthConfigurationError",
    "AuthError",
    "AuthenticationError",
    "CloudflareAccessAuthenticator",
    "CloudflareAccessConfig",
    "IdentityContext",
    "LocalAuthConfig",
    "LocalAuthenticator",
    "LocalUserRecord",
    "Role",
    "derive_local_user_id",
    "extract_access_token",
    "hash_password",
    "parse_local_users",
    "parse_role_mapping",
    "update_local_users_file",
    "verify_password",
]
