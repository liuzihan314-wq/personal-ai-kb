"""File-based storage primitives for immutable source material."""

from pkb.storage.raw import RawPaths, RawStorage, RawStorageError
from pkb.storage.users import (
    UserScopeError,
    prepare_user_root,
    resolve_user_root,
    user_root_for_identity,
    validate_user_id,
)

__all__ = [
    "RawPaths",
    "RawStorage",
    "RawStorageError",
    "UserScopeError",
    "prepare_user_root",
    "resolve_user_root",
    "user_root_for_identity",
    "validate_user_id",
]
