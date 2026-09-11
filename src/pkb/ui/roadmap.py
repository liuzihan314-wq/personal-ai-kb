"""Read the project roadmap for the in-app progress dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_TASK_HEADING = re.compile(r"^##\s+(TASK-\d+)\s+—\s+(.+?)\s*$", re.MULTILINE)
_FIELD = re.compile(r"^(Status|Dependencies|Owner|Progress|Acceptance record):\s*(.+?)\s*$", re.MULTILINE)
_TASK_ID = re.compile(r"TASK-\d+")


@dataclass(frozen=True)
class RoadmapTask:
    """A task extracted from the human-maintained ROADMAP.md file."""

    task_id: str
    title: str
    status: str
    dependencies: tuple[str, ...]
    owner: str | None
    annotation: str | None


def project_roadmap_path() -> Path:
    """Return the repository's canonical roadmap path."""

    return Path(__file__).resolve().parents[3] / "ROADMAP.md"


def parse_roadmap(markdown: str) -> list[RoadmapTask]:
    """Extract task status and its latest human-written note from Markdown."""

    headings = list(_TASK_HEADING.finditer(markdown))
    tasks: list[RoadmapTask] = []
    for index, heading in enumerate(headings):
        block_end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        block = markdown[heading.end() : block_end]
        fields = {name: value.strip().rstrip("  ") for name, value in _FIELD.findall(block)}
        dependencies = tuple(_TASK_ID.findall(fields.get("Dependencies", "")))
        tasks.append(
            RoadmapTask(
                task_id=heading.group(1),
                title=heading.group(2).strip(),
                status=fields.get("Status", "BACKLOG").upper(),
                dependencies=dependencies,
                owner=fields.get("Owner"),
                annotation=fields.get("Acceptance record") or fields.get("Progress"),
            )
        )
    return tasks


def load_roadmap(path: Path | None = None) -> list[RoadmapTask]:
    """Load the current roadmap from disk on every dashboard refresh."""

    return parse_roadmap((path or project_roadmap_path()).read_text(encoding="utf-8"))


__all__ = ["RoadmapTask", "load_roadmap", "parse_roadmap", "project_roadmap_path"]
