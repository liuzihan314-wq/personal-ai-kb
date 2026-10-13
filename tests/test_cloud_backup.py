import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile

import pytest

spec = importlib.util.spec_from_file_location(
    "cloud_backup", Path(__file__).resolve().parents[1] / "scripts/cloud_backup.py"
)
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def build_archive(tmp_path, members):
    path = tmp_path / "sample.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, content, kind in members:
            info = tarfile.TarInfo(name)
            if kind == "file":
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
            else:
                info.type = tarfile.SYMTYPE
                info.linkname = "../outside"
                archive.addfile(info)
    return path


def manifest_for(members):
    return {"files": {
        name: {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
        for name, content, _kind in members
    }}


def test_snapshot_preserves_pdf_text_and_index_bytes(tmp_path):
    members = [("raw/sample.pdf", b"%PDF-1.4\nsynthetic", "file"),
               ("notes/sample.md", "中文测试\n".encode(), "file"),
               ("index/index.json", b'{"entries":[]}', "file")]
    destination = tmp_path / "snapshot"
    backup.unpack_verified(build_archive(tmp_path, members), manifest_for(members), destination)
    for name, content, _kind in members:
        assert (destination / name).read_bytes() == content


@pytest.mark.parametrize("name", ["../outside", "/etc/passwd", "raw/../../outside", ".env", "config/invites.json"])
def test_snapshot_rejects_paths_outside_knowledge_layers(name):
    with pytest.raises(ValueError):
        backup.checked_path(name)


def test_snapshot_rejects_corruption_and_missing_files(tmp_path):
    members = [("index/index.json", b"{}", "file")]
    manifest = manifest_for(members)
    manifest["files"]["index/index.json"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash_mismatch"):
        backup.unpack_verified(build_archive(tmp_path, members), manifest, tmp_path / "corrupt")
    manifest = manifest_for(members)
    manifest["files"]["raw/missing.json"] = {"size": 1, "sha256": "0" * 64}
    with pytest.raises(ValueError, match="missing_files"):
        backup.unpack_verified(build_archive(tmp_path, members), manifest, tmp_path / "missing")


def test_snapshot_rejects_links_and_duplicate_files(tmp_path):
    members = [("index/index.json", b"{}", "file"), ("raw/link", b"", "link")]
    with pytest.raises(ValueError, match="unexpected_archive_member"):
        backup.unpack_verified(build_archive(tmp_path, members), manifest_for(members), tmp_path / "links")
    members = [("index/index.json", b"{}", "file")] * 2
    with pytest.raises(ValueError, match="unexpected_archive_member"):
        backup.unpack_verified(build_archive(tmp_path, members), manifest_for(members), tmp_path / "duplicates")


def test_snapshot_never_overwrites_existing_file(tmp_path):
    members = [("index/index.json", b"{}", "file")]
    destination = tmp_path / "existing"
    (destination / "index").mkdir(parents=True)
    (destination / "index/index.json").write_bytes(b"original")
    with pytest.raises(FileExistsError):
        backup.unpack_verified(build_archive(tmp_path, members), manifest_for(members), destination)
    assert (destination / "index/index.json").read_bytes() == b"original"
