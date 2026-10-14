import asyncio
import io
import json
from pathlib import Path
import tarfile
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from starlette.applications import Starlette

from pkb import backup, backup_client


def sample_root(tmp_path):
    root = tmp_path / "cloud"
    for name, content in {
        "raw/sample.pdf": b"%PDF-1.4\nsynthetic PDF",
        "raw/sample.json": b'{"id":"sample","original_file":"/data/cloud/raw/sample.pdf"}',
        "notes/sample.md": "# 中文笔记\n原文来源保留。\n".encode(),
        "index/index.json": b'{"entries":[]}',
        "history/sample.json": b'{"status":"ok"}',
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (root / ".env").write_text("DO_NOT_EXPORT=synthetic-secret")
    return root


def request(app, path, token=None, method="GET"):
    async def run():
        messages = []
        headers = [] if token is None else [(b"authorization", ("Bearer " + token).encode())]
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
                 "http_version": "1.1", "method": method, "scheme": "https",
                 "path": path, "raw_path": path.encode(), "query_string": b"",
                 "headers": headers, "client": ("127.0.0.1", 1), "server": ("localhost", 443)}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await app(scope, receive, send)
        status = next(x["status"] for x in messages if x["type"] == "http.response.start")
        body = b"".join(x.get("body", b"") for x in messages if x["type"] == "http.response.body")
        return status, body

    return asyncio.run(run())


@pytest.mark.parametrize("path", ["/api/backup/manifest", "/api/backup/snapshot", "/api/backup/rebuild-status"])
@pytest.mark.parametrize("token", [None, "wrong-key"])
def test_unauthorized_backup_never_returns_private_data(tmp_path, path, token):
    root = sample_root(tmp_path)
    app = Starlette(routes=backup.routes(root, "test-only-key"))
    status, body = request(app, path, token)
    assert status == 401
    assert b"sample" not in body
    assert "test-only-key".encode() not in body


def test_missing_server_key_disables_backup(tmp_path):
    app = Starlette(routes=backup.routes(sample_root(tmp_path), ""))
    assert request(app, "/api/backup/manifest", "test-only-key")[0] == 503


def test_authenticated_archive_preserves_source_links_and_pdf(tmp_path):
    root = sample_root(tmp_path)
    app = Starlette(routes=backup.routes(root, "test-only-key"))
    status, payload = request(app, "/api/backup/snapshot", "test-only-key")
    assert status == 200
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        names = archive.getnames()
        assert ".env" not in names
        assert set(names) == {"manifest.json", *backup.inventory(root)}
        for name in names:
            if name != "manifest.json":
                assert archive.extractfile(name).read() == (root / name).read_bytes()
    assert not backup.SNAPSHOT_LOCK.locked()


def test_source_changed_during_export_rejects_snapshot(tmp_path, monkeypatch):
    root = sample_root(tmp_path)
    original = backup.inventory
    calls = []

    def changed(path):
        calls.append(1)
        if len(calls) == 2:
            (root / "notes/sample.md").write_bytes(b"changed")
        return original(path)

    monkeypatch.setattr(backup, "inventory", changed)
    app = Starlette(routes=backup.routes(root, "test-only-key"))
    assert request(app, "/api/backup/snapshot", "test-only-key")[0] == 503
    assert not backup.SNAPSHOT_LOCK.locked()


def test_snapshot_rejects_source_symlink(tmp_path):
    root = sample_root(tmp_path)
    (root / "raw/link").symlink_to(root / ".env")
    with pytest.raises(ValueError, match="unsafe_link"):
        backup.snapshot(root)


def test_mac_backup_is_idempotent_and_keeps_previous_on_failure(tmp_path, monkeypatch):
    root = sample_root(tmp_path)
    manifest = backup.make_manifest(root)
    with backup.snapshot(root) as archive:
        payload = archive.read()
    calls = []

    class Opener:
        fail = False

        def open(self, req, timeout):
            calls.append(req.full_url)
            if self.fail:
                raise HTTPError(req.full_url, 401, "synthetic rejection", {}, None)
            return io.BytesIO(json.dumps(manifest).encode() if req.full_url.endswith("/manifest") else payload)

    opener = Opener()
    monkeypatch.setattr(backup_client, "build_opener", lambda *_args: opener)
    project = tmp_path / "mac"
    original = project / "data/raw/original.json"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"original Mac data")
    key = tmp_path / "test.key"
    key.write_text("test-only-key")
    key.chmod(0o600)
    assert backup_client.backup(project, "https://example.test", key) == 0
    saved = json.loads((project / "runtime/cloud-backup/status.json").read_text())
    path = Path(saved["snapshot"])
    assert backup_client.local_snapshot_valid(path, manifest["fingerprint"])
    assert backup_client.backup(project, "https://example.test", key) == 0
    assert len(list((project / "data/cloud-backup").iterdir())) == 1
    assert len(calls) == 3
    opener.fail = True
    assert backup_client.backup(project, "https://example.test", key) == 1
    status = json.loads((project / "runtime/cloud-backup/status.json").read_text())
    assert status["status"] == "failed"
    assert status["snapshot"] == saved["snapshot"]
    assert status["last_error"] == "HTTP_401"
    assert original.read_bytes() == b"original Mac data"


def test_cross_origin_redirect_is_refused():
    with pytest.raises(HTTPError):
        backup_client.NoRedirect().redirect_request(Request("https://example.test"), None, 302, "redirect", {}, "https://other.test")
