"""Data models shared by knowledge-base adapters and storage."""

from pkb.models.document import UnifiedDocument
from pkb.models.identity import IdentityContext, Role

__all__ = ["IdentityContext", "Role", "UnifiedDocument"]
