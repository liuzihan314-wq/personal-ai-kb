"""Command-line entry points for the project foundation."""

import logging

import typer

from pkb.config import Settings, get_settings
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


def main() -> None:
    """Invoke the Typer application."""

    app()


if __name__ == "__main__":
    main()
