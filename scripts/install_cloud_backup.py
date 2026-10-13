"""Install the explicitly authorized user launchd task without replacing files."""

from pathlib import Path
import os
import plistlib
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]


def main():
    target = Path.home() / "Library/LaunchAgents/com.personal-ai-kb.cloud-backup.plist"
    log_dir = PROJECT / "runtime/cloud-backup"
    log_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": "com.personal-ai-kb.cloud-backup",
        "ProgramArguments": [str(PROJECT / ".venv/bin/python"), str(PROJECT / "scripts/cloud_backup.py")],
        "WorkingDirectory": str(PROJECT),
        "RunAtLoad": True,
        "StartInterval": 3600,
        "StandardOutPath": str(log_dir / "schedule.log"),
        "StandardErrorPath": str(log_dir / "schedule-error.log"),
        "ProcessType": "Background",
        "Umask": 0o077,
    }
    template = log_dir / "job.plist"
    with template.open("wb") as stream:
        plistlib.dump(payload, stream)
    if "--prepare" in sys.argv:
        print("Prepared launchd template; no system change.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        plistlib.dump(payload, stream)
    target.chmod(0o600)
    subprocess.run(["/bin/launchctl", "bootstrap", "gui/" + str(os.getuid()), str(target)], check=True)
    print("Hourly cloud-backup task installed.")


if __name__ == "__main__":
    main()
