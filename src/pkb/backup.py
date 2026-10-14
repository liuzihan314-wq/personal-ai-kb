"""Read-only, authenticated snapshots of the current single-user data root."""

from datetime import datetime, timezone
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import threading

from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route
from starlette.background import BackgroundTask

LAYERS = ("raw", "notes", "knowledge", "index", "history")
SNAPSHOT_LOCK = threading.Lock()
NO_CACHE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def fingerprint(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def inventory(root):
    root = Path(root)
    if root.is_symlink():
        raise ValueError("unsafe_root")
    records = {}
    for layer in LAYERS:
        directory = root / layer
        if directory.is_symlink():
            raise ValueError("unsafe_layer")
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError("unsafe_link")
            if not path.is_file():
                continue
            if any(part.startswith(".env") for part in path.relative_to(root).parts):
                raise ValueError("configuration_in_data")
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            records[path.relative_to(root).as_posix()] = {
                "size": path.stat().st_size, "sha256": digest.hexdigest()
            }
    if "index/index.json" not in records:
        raise ValueError("missing_index")
    return records


def make_manifest(root):
    files = inventory(root)
    return {
        "schema_version": 1, "cloud_root": str(root), "files": files,
        "fingerprint": fingerprint(files),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "restore_note": "Original IDs, bodies and source links preserved; rebase cloud paths before local integration.",
    }


def snapshot(root):
    manifest = make_manifest(root)
    stream = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024, mode="w+b")
    try:
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            content = json.dumps(manifest, ensure_ascii=False).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(content)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(content))
            for relative in manifest["files"]:
                archive.add(Path(root) / relative, arcname=relative, recursive=False)
        if manifest["files"] != inventory(root):
            raise ValueError("source_changed")
        stream.seek(0)
        return stream
    except Exception:
        stream.close()
        raise


def denied(request, token):
    if not token:
        return JSONResponse({"error": "backup_disabled"}, status_code=503, headers=NO_CACHE)
    actual = request.headers.get("Authorization", "").encode()
    if not hmac.compare_digest(actual, ("Bearer " + token).encode()):
        return JSONResponse({"error": "unauthorized"}, status_code=401, headers=NO_CACHE)
    if request.method != "GET":
        return JSONResponse({"error": "method_not_allowed"}, status_code=405, headers=NO_CACHE)
    return None


def routes(root=None, token=None):
    data_root = Path(root or os.getenv("PKB_DATA_DIR", "data"))
    credential = token if token is not None else os.getenv("PKB_BACKUP_TOKEN", "")

    def manifest_route(request):
        refusal = denied(request, credential)
        if refusal is not None:
            return refusal
        try:
            return JSONResponse(make_manifest(data_root), headers=NO_CACHE)
        except Exception:
            return JSONResponse({"error": "snapshot_unavailable"}, status_code=503, headers=NO_CACHE)

    def snapshot_route(request):
        refusal = denied(request, credential)
        if refusal is not None:
            return refusal
        if not SNAPSHOT_LOCK.acquire(blocking=False):
            return JSONResponse({"error": "backup_busy"}, status_code=429, headers=NO_CACHE)
        try:
            stream = snapshot(data_root)
        except Exception:
            SNAPSHOT_LOCK.release()
            return JSONResponse({"error": "snapshot_unavailable"}, status_code=503, headers=NO_CACHE)

        closed = False

        def close():
            nonlocal closed
            if not closed:
                closed = True
                stream.close()
                SNAPSHOT_LOCK.release()

        def chunks():
            try:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    yield chunk
            finally:
                close()

        return StreamingResponse(chunks(), media_type="application/gzip", headers=NO_CACHE,
                                 background=BackgroundTask(close))

    def rebuild_status_route(request):
        refusal = denied(request, credential)
        if refusal is not None:
            return refusal
        path = data_root / "maintenance/notes-rebuild/task-047-cloud/status.json"
        if not path.exists():
            return JSONResponse({"status": "not_started"}, headers=NO_CACHE)
        return JSONResponse(json.loads(path.read_text()), headers=NO_CACHE)

    return [Route("/api/backup/rebuild-status", rebuild_status_route, methods=["GET"]),
            Route("/api/backup/manifest", manifest_route, methods=["GET"]),
            Route("/api/backup/snapshot", snapshot_route, methods=["GET"])]
