"""Trusted identity and role values produced by an authentication adapter."""

from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    """The only application roles supported by the V2 first slice."""

    ADMIN = "admin"
    MEMBER = "member"

    @property
    def display_name(self) -> str:
        """Return the user-facing Chinese label without exposing raw claims."""

        return "管理员" if self is Role.ADMIN else "成员"


@dataclass(frozen=True, slots=True)
class IdentityContext:
    """A verified request identity safe to pass to later user-scoped layers.

    ``user_id`` is derived from the configured issuer and verified subject.  A
    raw email or full JWT is deliberately not retained here.  ``subject`` and
    ``issuer`` are kept only for adapter and audit correlation and are excluded
    from the default representation so accidental logs do not expose them.
    """

    user_id: str
    role: Role
    display_name: str
    issuer: str = field(repr=False)
    subject: str = field(repr=False)
    email: str | None = None

    @property
    def is_admin(self) -> bool:
        """Return whether this context has the explicitly mapped admin role."""

        return self.role is Role.ADMIN
