"""Mac HTTPS client for verified, append-only knowledge snapshots."""

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import ssl
import sys
import tarfile
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler
import uuid

import certifi

from pkb.backup import fingerprint

PROJECT = Path(__file__).resolve().parents[2]
BASE_URL = "https://knowledge-base-trial-trial.up.railway.app"
KEY_FILE = Path.home() / ".config/personal-ai-kb/cloud-backup.key"
LAYERS = {"raw", "notes", "knowledge", "index", "history"}


def checked_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] not in LAYERS:
        raise ValueError("unsafe_archive_path")
    if str(path) != name or len(path.parts) < 2:
        raise ValueError("invalid_archive_path")
    return path


def unpack_verified(archive_path, manifest, destination):
    files = manifest["files"]
    if not isinstance(files, dict) or "index/index.json" not in files:
        raise ValueError("invalid_manifest")
    for name in files:
        checked_path(name)
    observed = set()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            if member.name == "manifest.json":
                if not member.isfile() or member.size > 10 * 1024 * 1024 or member.name in observed:
                    raise ValueError("invalid_archive_manifest")
                source = archive.extractfile(member)
                embedded = json.loads(source.read())
                if embedded["files"] != files or embedded["fingerprint"] != fingerprint(files):
                    raise ValueError("manifest_mismatch")
                observed.add(member.name)
                continue
            checked_path(member.name)
            if not member.isfile() or member.name not in files or member.name in observed:
                raise ValueError("unexpected_archive_member")
            expected = files[member.name]
            if member.size != expected["size"]:
                raise ValueError("size_mismatch")
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            digest = hashlib.sha256()
            with source, target.open("xb") as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)
                    digest.update(chunk)
            if digest.hexdigest() != expected["sha256"]:
                raise ValueError("hash_mismatch")
            observed.add(member.name)
    if observed - {"manifest.json"} != set(files):
        raise ValueError("missing_files")


def local_snapshot_valid(path, expected):
    try:
        manifest = json.loads((path / "manifest.json").read_text())
        if manifest["fingerprint"] != expected or fingerprint(manifest["files"]) != expected:
            return False
        for name, item in manifest["files"].items():
            checked_path(name)
            target = path / name
            if target.is_symlink() or not target.is_file() or target.stat().st_size != item["size"]:
                return False
            digest = hashlib.sha256()
            with target.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != item["sha256"]:
                return False
        return True
    except Exception:
        return False


def write_json(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".pending")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)


def now():
    return datetime.now(timezone.utc).isoformat()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Backup redirects refused", headers, fp)


def backup(project=None, base_url=BASE_URL, key_file=KEY_FILE):
    project = Path(project or PROJECT)
    if not base_url.startswith("https://"):
        raise ValueError("https_required")
    os.umask(0o077)
    state_dir = project / "runtime/cloud-backup"
    state_dir.mkdir(parents=True, exist_ok=True)
    with (state_dir / "backup.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Backup already running; skipped.")
            return 0
        status_path = state_dir / "status.json"
        prior = json.loads(status_path.read_text()) if status_path.exists() else {}
        try:
            token = Path(key_file).read_text().strip()
            if not token or Path(key_file).stat().st_mode & 0o077:
                raise ValueError("unsafe_or_missing_credential")
            opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))

            def request(path):
                return opener.open(Request(base_url.rstrip("/") + path, headers={"Authorization": "Bearer " + token}), timeout=90)

            with request("/api/backup/manifest") as response:
                manifest = json.loads(response.read(10 * 1024 * 1024))
            if manifest.get("schema_version") != 1 or fingerprint(manifest["files"]) != manifest["fingerprint"]:
                raise ValueError("invalid_manifest")
            snapshot_path = Path(prior.get("snapshot", "/nonexistent-cloud-snapshot"))
            if manifest["fingerprint"] == prior.get("fingerprint") and local_snapshot_valid(snapshot_path, manifest["fingerprint"]):
                prior.update(last_check=now(), status="unchanged", last_error=None)
                write_json(status_path, prior)
                print("Cloud unchanged; existing local snapshot integrity checked.")
                return 0
            run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
            task_dir = project / ".tmp/cloud-backup" / run_id
            task_dir.mkdir(parents=True, exist_ok=False)
            archive_path = task_dir / "data.tar.gz"
            deadline = time.monotonic() + 600
            with request("/api/backup/snapshot") as response, archive_path.open("xb") as archive:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    if time.monotonic() > deadline:
                        raise TimeoutError("download_timeout")
                    archive.write(chunk)
            staging = task_dir / "snapshot"
            staging.mkdir()
            unpack_verified(archive_path, manifest, staging)
            manifest["saved_at"] = now()
            write_json(staging / "manifest.json", manifest)
            snapshots = project / "data/cloud-backup"
            snapshots.mkdir(parents=True, exist_ok=True)
            destination = snapshots / run_id
            staging.rename(destination)
            write_json(status_path, {
                "status": "success", "last_check": now(), "last_success": now(),
                "snapshot": str(destination), "fingerprint": manifest["fingerprint"],
                "file_count": len(manifest["files"]),
                "bytes": sum(item["size"] for item in manifest["files"].values()),
                "last_error": None,
            })
            print("Verified cloud backup saved: " + str(destination))
            return 0
        except Exception as exc:
            error = "HTTP_" + str(exc.code) if isinstance(exc, HTTPError) else type(exc).__name__
            prior.update(status="failed", last_check=now(), last_error=error)
            write_json(status_path, prior)
            print("Backup failed (" + error + "); previous snapshots retained.", file=sys.stderr)
            return 1


def main():
    parser = argparse.ArgumentParser(description="Download verified HTTPS knowledge snapshots.")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        path = PROJECT / "runtime/cloud-backup/status.json"
        print(path.read_text(encoding="utf-8") if path.exists() else "No backup has run yet.")
        return 0
    return backup()
