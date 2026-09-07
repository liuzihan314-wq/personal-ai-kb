"""Command-line entry points for the project foundation."""

import json
import logging
from pathlib import Path

import typer

from pkb.config import Settings, get_settings
from pkb.ingest.idea import IdeaCardError, IdeaCardImporter
from pkb.ingest.pdf import PDFImportError, PDFImporter
from pkb.index import IndexBuildError, IndexService, IndexStorageError, read_index
from pkb.logging_config import configure_logging
from pkb.notes import NoteGenerationError, NoteService, NoteStorageError
from pkb.qa import QAError, QAService
from pkb.retrieval import RetrievalService
from pkb.scripts import ScriptGenerationError, ScriptWriter
from pkb.storage import RawStorage
from pkb.topics import TopicGenerationError, TopicGenerator


app = typer.Typer(
    name="pkb",
    help="Personal AI Knowledge Base command-line tools.",
    no_args_is_help=True,
    add_completion=False,
)
logger = logging.getLogger(__name__)


def _load_settings() -> Settings:
    settings = get_settings()
    configure_logging(settings.log_level)
    return settings


@app.command()
def hello(
    name: str = typer.Option("World", "--name", "-n", help="Name to greet."),
) -> None:
    """Print a small greeting to verify the installed CLI."""

    _load_settings()
    logger.debug("Running hello command")
    typer.echo(f"Hello, {name}!")


@app.command()
def health() -> None:
    """Load configuration and report a minimal healthy application state."""

    settings = _load_settings()
    logger.debug("Running health check")
    typer.echo("status: ok")
    typer.echo(f"app: {settings.app_name}")
    typer.echo(f"environment: {settings.environment}")
    typer.echo(f"data_dir: {settings.data_dir}")


@app.command("import-pdf")
def import_pdf(
    file_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to a PDF with an extractable text layer.",
    ),
) -> None:
    """Import one text PDF into immutable local Raw storage."""

    settings = _load_settings()
    try:
        document = PDFImporter(raw_dir=settings.raw_dir).import_file(file_path)
    except PDFImportError as exc:
        raise typer.BadParameter(str(exc), param_hint="file_path") from exc

    typer.echo("status: imported")
    typer.echo(f"id: {document.id}")
    typer.echo(f"title: {document.title}")
    typer.echo(f"raw_pdf: {document.original_file}")
    typer.echo(f"raw_text: {document.metadata['extracted_text_file']}")
    typer.echo(f"metadata: {document.metadata['metadata_file']}")


@app.command("add-idea")
def add_idea(
    content: str = typer.Argument(..., help="原始观点、好句或灵感正文。"),
    source_url: str | None = typer.Option(
        None,
        "--source-url",
        "--source",
        help="可选的来源 URL。",
    ),
    tags: list[str] = typer.Option(
        [],
        "--tag",
        "--tags",
        "-t",
        help="可选标签；可重复传入，也可用逗号分隔。",
    ),
    note: str | None = typer.Option(None, "--note", help="可选的个人备注。"),
) -> None:
    """Save one manually entered idea card into immutable local Raw storage."""

    settings = _load_settings()
    parsed_tags = [
        tag_part.strip()
        for tag in tags
        for tag_part in tag.split(",")
        if tag_part.strip()
    ]
    try:
        document = IdeaCardImporter(raw_dir=settings.raw_dir).create(
            content,
            source_url=source_url,
            tags=parsed_tags,
            note=note,
        )
    except IdeaCardError as exc:
        raise typer.BadParameter(str(exc), param_hint="content") from exc

    typer.echo("status: saved")
    typer.echo(f"id: {document.id}")
    typer.echo(f"content_type: {document.content_type}")
    typer.echo(f"source_type: {document.source_type}")
    typer.echo(f"raw_text: {document.original_file}")
    typer.echo(f"metadata: {document.metadata['metadata_file']}")


app.command("create-idea")(add_idea)


@app.command("generate-note")
def generate_note(
    document_id: str = typer.Argument(..., help="已保存 Raw 文档的 ID。"),
) -> None:
    """Generate one local Markdown Note from an existing Raw document."""

    settings = _load_settings()
    try:
        document = RawStorage(settings.raw_dir).load_document(document_id)
    except FileNotFoundError as exc:
        raise typer.BadParameter(
            f"找不到完整的 Raw 文档：{document_id}",
            param_hint="document_id",
        ) from exc

    try:
        result = NoteService(notes_dir=settings.notes_dir).generate(document)
    except (NoteGenerationError, NoteStorageError) as exc:
        raise typer.BadParameter(str(exc), param_hint="document_id") from exc

    typer.echo("status: generated" if result.created else "status: existing")
    typer.echo(f"id: {result.note.document_id}")
    typer.echo(f"title: {result.note.title}")
    typer.echo(f"source_type: {result.note.source_type}")
    typer.echo(f"note: {result.path}")


@app.command("rebuild-index")
def rebuild_index(
    notes_dir: Path | None = typer.Option(
        None,
        "--notes-dir",
        help="Override the configured Markdown Notes directory.",
    ),
    index_path: Path | None = typer.Option(
        None,
        "--index-path",
        help="Override the output JSON index path.",
    ),
) -> None:
    """Rebuild the local JSON index from the current Markdown Notes."""

    settings = _load_settings()
    target_notes_dir = notes_dir or settings.notes_dir
    target_index_path = index_path or settings.index_dir / "index.json"
    try:
        index = IndexService(
            notes_dir=target_notes_dir,
            index_path=target_index_path,
        ).rebuild()
    except (IndexBuildError, IndexStorageError) as exc:
        raise typer.BadParameter(str(exc), param_hint="notes_dir") from exc

    typer.echo("status: rebuilt")
    typer.echo(f"notes: {len(index.entries)}")
    typer.echo(f"related: {index.related_count}")
    typer.echo(f"index: {target_index_path}")


@app.command("index-status")
def index_status(
    index_path: Path | None = typer.Option(
        None,
        "--index-path",
        help="Override the configured JSON index path.",
    ),
) -> None:
    """Read the local JSON index and report its current size."""

    settings = _load_settings()
    target_index_path = index_path or settings.index_dir / "index.json"
    try:
        index = read_index(target_index_path)
    except FileNotFoundError as exc:
        raise typer.BadParameter(
            f"JSON index does not exist: {target_index_path}",
            param_hint="index_path",
        ) from exc
    except IndexStorageError as exc:
        raise typer.BadParameter(str(exc), param_hint="index_path") from exc

    typer.echo("status: ok")
    typer.echo(f"notes: {len(index.entries)}")
    typer.echo(f"related: {index.related_count}")
    typer.echo(f"index: {target_index_path}")


@app.command("search")
def search(
    query: str = typer.Argument(..., help="要检索的问题或关键词。"),
    index_path: Path | None = typer.Option(
        None,
        "--index-path",
        help="Override the configured JSON index path.",
    ),
    limit: int = typer.Option(10, "--limit", min=1, help="最多返回的候选数量。"),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="以 JSON 输出完整的可追溯候选结果。",
    ),
) -> None:
    """Search the local JSON Index with deterministic explainable scoring."""

    settings = _load_settings()
    target_index_path = index_path or settings.index_dir / "index.json"
    try:
        result = RetrievalService(target_index_path).search(query, limit=limit)
    except FileNotFoundError as exc:
        raise typer.BadParameter(
            f"JSON index does not exist: {target_index_path}",
            param_hint="index_path",
        ) from exc
    except IndexStorageError as exc:
        raise typer.BadParameter(str(exc), param_hint="index_path") from exc

    if as_json:
        typer.echo(
            json.dumps(
                result.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
        return

    typer.echo(f"status: {result.status}")
    typer.echo(f"query: {result.query}")
    typer.echo(f"candidates: {len(result.candidates)}")
    for candidate in result.candidates:
        typer.echo(f"- document_id: {candidate.document_id}")
        typer.echo(f"  raw_document_id: {candidate.raw_document_id}")
        typer.echo(f"  title: {candidate.title}")
        typer.echo(f"  score: {candidate.score:.4f}")
        typer.echo(f"  note: {candidate.note_path}")
        for field in candidate.evidence.matched_fields:
            values = ", ".join(getattr(candidate.evidence, field))
            typer.echo(f"  evidence_{field}: {values}")
        for reason in candidate.reasons:
            typer.echo(f"  reason_{reason.field}: {reason.explanation}")


# ``retrieve`` is a CLI spelling kept for callers that use the service name.
app.command("retrieve")(search)


@app.command("ask")
def ask(
    question: str = typer.Argument(..., help="要回答的问题。"),
    index_path: Path | None = typer.Option(
        None,
        "--index-path",
        help="Override the configured JSON index path.",
    ),
    knowledge_dir: Path | None = typer.Option(
        None,
        "--knowledge-dir",
        help="Override the configured Topic Knowledge directory.",
    ),
    notes_dir: Path | None = typer.Option(
        None,
        "--notes-dir",
        help="Override the configured Markdown Notes directory.",
    ),
    raw_dir: Path | None = typer.Option(
        None,
        "--raw-dir",
        help="Override the configured immutable Raw directory.",
    ),
    limit: int = typer.Option(10, "--limit", min=1, help="最多使用的检索候选数量。"),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="以 JSON 输出回答、证据和来源链。",
    ),
) -> None:
    """Answer a question using local Knowledge, Notes, and Raw evidence."""

    settings = _load_settings()
    service = QAService(
        index_path=index_path or settings.index_dir / "index.json",
        knowledge_dir=knowledge_dir or settings.knowledge_dir,
        notes_dir=notes_dir or settings.notes_dir,
        raw_dir=raw_dir or settings.raw_dir,
    )
    try:
        result = service.answer(question, limit=limit)
    except QAError as exc:
        raise typer.BadParameter(str(exc), param_hint="question") from exc

    if as_json:
        typer.echo(
            json.dumps(
                result.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
        return

    typer.echo(f"status: {result.status}")
    typer.echo(f"question: {result.question}")
    typer.echo(f"evidence_level: {result.evidence_level}")
    if result.answer is not None:
        typer.echo(f"answer: {result.answer}")
    else:
        typer.echo(f"reason: {result.reason}")
    typer.echo(f"sources: {len(result.sources)}")
    for source in result.sources:
        location = source.path or source.reference or source.source_id
        availability = "available" if source.available else "unavailable"
        typer.echo(
            f"- {source.kind}: {source.source_id} ({availability}) {location}"
        )
    for item in result.evidence:
        typer.echo(f"evidence_{item.source_kind}: {item.explanation}")


app.command("qa")(ask)
app.command("answer")(ask)


@app.command("generate-topics")
def generate_topics_command(
    index_path: Path | None = typer.Option(
        None,
        "--index-path",
        help="Override the configured JSON index path.",
    ),
    knowledge_dir: Path | None = typer.Option(
        None,
        "--knowledge-dir",
        help="Override the local Topic Knowledge directory.",
    ),
    notes_dir: Path | None = typer.Option(
        None,
        "--notes-dir",
        help="Override the local Markdown Notes directory.",
    ),
    limit: int = typer.Option(
        5,
        "--limit",
        min=3,
        max=5,
        help="最多返回 3～5 个候选选题。",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="以 JSON 输出完整的可追溯候选结果。",
    ),
) -> None:
    """Generate explainable content topics from local Index, Knowledge, and Notes."""

    settings = _load_settings()
    target_index_path = index_path or settings.index_dir / "index.json"
    target_knowledge_dir = knowledge_dir or settings.knowledge_dir
    target_notes_dir = notes_dir or settings.notes_dir
    try:
        result = TopicGenerator(
            index_path=target_index_path,
            knowledge_dir=target_knowledge_dir,
            notes_dir=target_notes_dir,
        ).generate(limit=limit)
    except TopicGenerationError as exc:
        raise typer.BadParameter(str(exc), param_hint="index_path") from exc

    if as_json:
        typer.echo(
            json.dumps(
                result.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
        return

    typer.echo(f"status: {result.status}")
    typer.echo(f"message: {result.message}")
    typer.echo(f"candidates: {len(result.candidates)}")
    for rank, candidate in enumerate(result.candidates, start=1):
        typer.echo(f"- rank: {rank}")
        typer.echo(f"  title: {candidate.title}")
        typer.echo(f"  score: {candidate.score:.4f}")
        typer.echo(f"  why_worth_doing: {candidate.why_worth_doing}")
        for source in candidate.sources:
            typer.echo(
                f"  source_{source.kind}: {source.source_id} ({source.path})"
            )
        for evidence in candidate.evidence:
            typer.echo(
                f"  evidence_{evidence.signal}: {', '.join(evidence.values)}"
            )
        for reason in candidate.reasons:
            typer.echo(f"  reason_{reason.rule}: {reason.explanation}")


@app.command("write-script")
def write_script_command(
    topic: str | None = typer.Argument(
        None,
        help="已选择的 TopicCandidate 标题或稳定 ID。",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        "--confirmed",
        help="确认这是用户人工选择的选题；未传入时不会生成口播。",
    ),
    index_path: Path | None = typer.Option(
        None,
        "--index-path",
        help="Override the configured JSON index path.",
    ),
    knowledge_dir: Path | None = typer.Option(
        None,
        "--knowledge-dir",
        help="Override the local Topic Knowledge directory.",
    ),
    notes_dir: Path | None = typer.Option(
        None,
        "--notes-dir",
        help="Override the local Markdown Notes directory.",
    ),
    raw_dir: Path | None = typer.Option(
        None,
        "--raw-dir",
        help="Override the immutable Raw directory.",
    ),
    limit: int = typer.Option(10, "--limit", min=1, help="最多使用的二次检索候选数量。"),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="以 JSON 输出完整的口播、检索结果和来源链。",
    ),
) -> None:
    """Write a traceable 2–3 minute script after explicit topic confirmation."""

    settings = _load_settings()
    service = ScriptWriter(
        index_path=index_path or settings.index_dir / "index.json",
        knowledge_dir=knowledge_dir or settings.knowledge_dir,
        notes_dir=notes_dir or settings.notes_dir,
        raw_dir=raw_dir or settings.raw_dir,
    )
    try:
        result = service.write(topic, confirmed=confirm, limit=limit)
    except ScriptGenerationError as exc:
        raise typer.BadParameter(str(exc), param_hint="topic") from exc

    if as_json:
        typer.echo(
            json.dumps(
                result.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
        )
        return

    typer.echo(f"status: {result.status}")
    typer.echo(f"selection_confirmed: {result.selection_confirmed}")
    if result.topic:
        typer.echo(f"topic: {result.topic}")
    typer.echo(f"message: {result.message}")
    if result.script:
        typer.echo("script:")
        typer.echo(result.script)
    typer.echo(f"sources: {len(result.sources)}")
    for source in result.sources:
        location = source.path or source.reference or source.source_id
        availability = "available" if source.available else "unavailable"
        typer.echo(f"- {source.kind}: {source.source_id} ({availability}) {location}")
    for item in result.evidence:
        typer.echo(f"evidence_{item.source_kind}: {item.explanation}")


def main() -> None:
    """Invoke the Typer application."""

    app()


if __name__ == "__main__":
    main()
