"""Command-line entry points for the project foundation."""

import logging
from pathlib import Path

import typer

from pkb.config import Settings, get_settings
from pkb.ingest.pdf import PDFImportError, PDFImporter
from pkb.logging_config import configure_logging


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


def main() -> None:
    """Invoke the Typer application."""

    app()


if __name__ == "__main__":
    main()
