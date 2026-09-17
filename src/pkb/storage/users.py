"""User-scoped storage roots for the V2 multi-user slice.

Every read/write entry point in V2 binds to the current user root *before*
any business operation runs.  The root is always derived from the verified
server-side identity context—never from form fields, query parameters,
upload filenames, or client state.  When no valid identity exists there is
no fallback to the shared V1 root: the caller fails closed instead.
"""

from pathlib import Path
import re

from pkb.config import Settings
from pkb.models import IdentityContext


class UserScopeError(RuntimeError):
    """Raised when a user storage root cannot be safely resolved or prepared."""


USER_ID_PATTERN = re.compile(r"^u_[0-9a-f]{64}$")
"""The only internal user id shape accepted by user-scoped storage.

Authentication adapters derive ids as ``"u_"`` plus the lowercase hex digest
of ``sha256(issuer + "\\0" + subject)``.  Anything else—empty values, emails,
path separators, ``..`` segments, or absolute paths—is rejected before it
can influence a filesystem location.
"""

USER_SUBDIRECTORIES: tuple[str, ...] = ("raw", "notes", "knowledge", "index", "history")
"""The isolated layout under each ``data/users/<user_id>/`` root.

``history/`` records are defined by TASK-030; the isolation boundary itself
is established here so no user content can ever land in a shared directory.
"""


def validate_user_id(user_id: object) -> str:
    """Return a path-safe internal user id or raise :class:`UserScopeError`."""

    if not isinstance(user_id, str) or not user_id:
        raise UserScopeError("缺少有效的用户身份")
    if not USER_ID_PATTERN.fullmatch(user_id):
        raise UserScopeError("用户身份格式无效")
    return user_id


def resolve_user_root(data_dir: str | Path, user_id: str) -> Path:
    """Bind one verified identity to ``<data_dir>/users/<user_id>/``.

    Defense in depth: even though ``user_id`` is pattern-validated first, the
    joined path must still live directly under the ``users`` directory after
    resolution, so a caller can never escape into the shared V1 root or
    another user's space.
    """

    safe_id = validate_user_id(user_id)
    users_dir = Path(data_dir) / "users"
    root = users_dir / safe_id
    if root.resolve().parent != users_dir.resolve():
        raise UserScopeError("用户目录越权")
    return root


def prepare_user_root(root: str | Path) -> Path:
    """Create the isolated layout for one user root and return it.

    Creating an empty layout for a *new* verified user is expected.  Any
    failure to create the directories is surfaced as a readable error instead
    of silently degrading to another location.  Error messages deliberately
    avoid absolute server paths.
    """

    root_path = Path(root)
    try:
        for name in USER_SUBDIRECTORIES:
            (root_path / name).mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise UserScopeError(
            f"用户数据目录不可用：{error.strerror or error.__class__.__name__}"
        ) from error
    return root_path


def user_root_for_identity(settings: Settings, identity: IdentityContext) -> Path:
    """Resolve (without creating) the user root for a verified identity."""

    return resolve_user_root(settings.data_dir, identity.user_id)
