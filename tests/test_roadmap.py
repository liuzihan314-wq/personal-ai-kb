from pathlib import Path

from pkb.ui.roadmap import load_roadmap, parse_roadmap


def test_parse_roadmap_reads_task_status_dependencies_and_annotation():
    tasks = parse_roadmap(
        """## TASK-101 — Import\n\nStatus: DONE  \nDependencies: TASK-100, TASK-099  \nOwner: Worker\n\nAcceptance record: Imported real PDFs.\n\n## TASK-102 — Publish\n\nStatus: READY\nDependencies: none\n\nProgress: Waiting for review.\n"""
    )

    assert [(task.task_id, task.status) for task in tasks] == [
        ("TASK-101", "DONE"),
        ("TASK-102", "READY"),
    ]
    assert tasks[0].dependencies == ("TASK-100", "TASK-099")
    assert tasks[0].annotation == "Imported real PDFs."
    assert tasks[1].dependencies == ()
    assert tasks[1].annotation == "Waiting for review."


def test_load_roadmap_uses_the_markdown_file(tmp_path: Path):
    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text("## TASK-200 — Dashboard\n\nStatus: IN_PROGRESS\n", encoding="utf-8")

    tasks = load_roadmap(roadmap)

    assert tasks[0].title == "Dashboard"
    assert tasks[0].status == "IN_PROGRESS"
