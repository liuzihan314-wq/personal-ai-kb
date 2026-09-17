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
    "Role",
    "extract_access_token",
    "parse_role_mapping",
]
