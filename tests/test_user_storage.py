"""Tests for user-scoped storage isolation (TASK-029)."""

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from pkb.config import Settings
from pkb.models import IdentityContext, Role
from pkb.providers import MockAIProvider
from pkb.storage import UserScopeError, prepare_user_root, user_root_for_identity
from pkb.ui import UIPaths, UIService


@pytest.fixture
def user_tmp_path() -> Path:
    """Yield a temporary directory inside the project worktree.

    The brokered sandbox blocks writes under the system temp root for some
    new test files, so we keep test scratch space inside the repository.
    """

    base = Path(__file__).parent / "_tmp"
    base.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=base, prefix="user-storage-") as directory:
        yield Path(directory)


def _user_id(issuer: str, subject: str) -> str:
    """Reproduce the internal id derivation used by auth adapters."""

    digest = sha256(f"{issuer}\0{subject}".encode("utf-8")).hexdigest()
    return f"u_{digest}"


def _identity(subject: str, role: Role = Role.MEMBER) -> IdentityContext:
    return IdentityContext(
        user_id=_user_id("https://test.example.com", subject),
        role=role,
        display_name=f"User {subject}",
        issuer="https://test.example.com",
        subject=subject,
        email=f"{subject}@example.com",
    )


def test_uipaths_v1_root_without_user_id(user_tmp_path: Path) -> None:
    """Legacy single-user layout is preserved when no identity is provided."""

    paths = UIPaths.from_data_dir(user_tmp_path)
    assert paths.raw_dir == user_tmp_path / "raw"
    assert paths.notes_dir == user_tmp_path / "notes"
    assert paths.knowledge_dir == user_tmp_path / "knowledge"
    assert paths.index_path == user_tmp_path / "index" / "index.json"
    assert paths.history_dir == user_tmp_path / "history"


def test_uipaths_v2_user_root_with_user_id(user_tmp_path: Path) -> None:
    """User-scoped layout isolates every content bucket under users/<id>."""

    user_id = _user_id("https://test.example.com", "alice")
    paths = UIPaths.from_data_dir(user_tmp_path, user_id=user_id)
    user_root = user_tmp_path / "users" / user_id
    assert paths.raw_dir == user_root / "raw"
    assert paths.notes_dir == user_root / "notes"
    assert paths.knowledge_dir == user_root / "knowledge"
    assert paths.index_path == user_root / "index" / "index.json"
    assert paths.history_dir == user_root / "history"


def test_uiservice_prepares_user_root(user_tmp_path: Path, monkeypatch) -> None:
    """Creating a service with an identity prepares the isolated layout."""

    settings = Settings(data_dir=str(user_tmp_path), log_level="INFO")
    monkeypatch.setattr("pkb.ui.services.get_settings", lambda: settings)

    identity = _identity("alice")
    service = UIService(identity=identity)

    user_root = user_tmp_path / "users" / identity.user_id
    assert service.paths.data_dir == user_root
    for name in ("raw", "notes", "knowledge", "index", "history"):
        assert (user_root / name).is_dir()


def test_user_data_is_not_visible_to_other_user(user_tmp_path: Path, monkeypatch) -> None:
    """Alice's idea must not appear in Bob's search results."""

    settings = Settings(data_dir=str(user_tmp_path), log_level="INFO")
    monkeypatch.setattr("pkb.ui.services.get_settings", lambda: settings)

    alice = UIService(identity=_identity("alice"), provider=MockAIProvider())
    alice.add_idea("Alice 的私有灵感", tags=["private"])

    bob = UIService(identity=_identity("bob"), provider=MockAIProvider())
    bob.add_idea("Bob 的私有灵感", tags=["private"])

    # Bob should only see his own note in the index.
    bob_result = bob.search("私有灵感")
    assert len(bob_result.candidates) == 1
    assert "Alice" not in bob_result.candidates[0].note_path

    # Alice should only see her own note.
    alice_result = alice.search("私有灵感")
    assert len(alice_result.candidates) == 1
    assert "Bob" not in alice_result.candidates[0].note_path

    # Bob searching for Alice's literal content finds nothing.
    assert bob.search("Alice").status == "no_hits"
    # Alice searching for Bob's literal content finds nothing.
    assert alice.search("Bob").status == "no_hits"


def test_identity_and_paths_are_mutually_exclusive() -> None:
    """UIService refuses ambiguous construction."""

    paths = UIPaths.from_data_dir("/tmp/pkb")
    identity = _identity("alice")
    with pytest.raises(ValueError, match="paths 和 identity 不能同时提供"):
        UIService(paths=paths, identity=identity)


def test_invalid_user_id_is_rejected(user_tmp_path: Path) -> None:
    """Malformed identifiers cannot influence filesystem paths."""

    for bad in ("", "alice@example.com", "../etc", "u_abc", "u_" + "x" * 64):
        with pytest.raises(UserScopeError):
            UIPaths.from_data_dir(user_tmp_path, user_id=bad)


def test_user_root_for_identity_uses_settings_data_dir(user_tmp_path: Path) -> None:
    """The resolved root lives under the configured data directory."""

    settings = Settings(data_dir=str(user_tmp_path), log_level="INFO")
    identity = _identity("alice")
    root = user_root_for_identity(settings, identity)
    assert root == user_tmp_path / "users" / identity.user_id


def test_prepare_user_root_creates_subdirectories(user_tmp_path: Path) -> None:
    """prepare_user_root creates the isolated layout on first access."""

    root = user_tmp_path / "users" / _user_id("https://test.example.com", "alice")
    prepare_user_root(root)
    assert (root / "raw").is_dir()
    assert (root / "notes").is_dir()
    assert (root / "knowledge").is_dir()
    assert (root / "index").is_dir()
    assert (root / "history").is_dir()
