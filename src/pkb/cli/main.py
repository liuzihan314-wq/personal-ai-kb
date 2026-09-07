"""Command-line entry points for the project foundation."""

import logging
from pathlib import Path

import typer

from pkb.config import Settings, get_settings
from pkb.ingest.idea import IdeaCardError, IdeaCardImporter
from pkb.ingest.pdf import PDFImportError, PDFImporter
from pkb.logging_config import configure_logging
from pkb.notes import NoteGenerationError, NoteService, NoteStorageError
from pkb.storage import RawStorage


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


def main() -> None:
    """Invoke the Typer application."""

    app()


if __name__ == "__main__":
    main()
