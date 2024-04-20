import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
from click_help_colors import HelpColorsGroup

from timetracker.api import Api, ApiError
from timetracker.config import Config
from timetracker.worklog.data import Activity
from timetracker.worklog.io import read_from_file, transact

ERROR = click.style("    error:", fg="red", bold=True)
CAUSED_BY = click.style("caused by:", bold=True)
NOTE = click.style("     note:", bold=True)


def report_error(e: Exception):
    def report_notes(e: BaseException):
        if hasattr(e, "__notes__"):
            for note in e.__notes__:
                click.echo(f"{NOTE} {note}", err=True)

    click.echo(f"{ERROR} {e}", err=True)
    report_notes(e)
    cause = e
    while (cause := cause.__cause__) is not None:
        click.echo(f"{CAUSED_BY} {cause}", err=True)
        report_notes(cause)


def cli_with_error_reporting():
    try:
        cli()
    except Exception as e:
        report_error(e)
        sys.exit(1)


WORKLOG_JSON_PATH = Path("~/Desktop/worklog.json").expanduser()


def ensure_activity(maybe_activity: Optional[Activity]) -> Activity:
    match maybe_activity:
        case None:
            return Activity(
                description=click.prompt("Description"),
                issue=click.prompt("Issue"),
            )
        case Activity():
            return maybe_activity


@click.group(
    cls=HelpColorsGroup,
    help_headers_color="yellow",
    help_options_color="green",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--config-file", type=click.Path(exists=True))
@click.pass_context
def cli(ctx: click.Context, config_file: Optional[Path]):
    if config_file is None:
        config_file = Path("~/.config/timetracker.json").expanduser()

    with open(config_file, "r") as config_stream:
        ctx.obj = Config.from_json(config_stream.read())


@cli.command()
def status():
    """Print a summary of the worklog by activity."""
    try:
        worklog = read_from_file(WORKLOG_JSON_PATH)
        click.echo(worklog)
    except FileNotFoundError:
        click.echo(
            "No worklog file has been created yet. Start an activity to create one."
        )


@cli.command()
@click.argument("activity")
def start(activity: str):
    """Start a new activity or resume an existing one."""
    with transact(WORKLOG_JSON_PATH) as worklog:
        worklog.update_activity(activity, lambda a: ensure_activity(a).started())


@cli.command()
@click.argument("activity")
def stop(activity: str):
    """Stop a running activity."""
    with transact(WORKLOG_JSON_PATH) as worklog:
        worklog.update_activity(activity, lambda a: Activity.verify(a).stopped())


@cli.command()
def reset():
    """Delete the worklog."""
    if click.confirm("This will delete the worklog. Proceed?"):
        WORKLOG_JSON_PATH.unlink()


@cli.command()
@click.option("--activity")
@click.pass_obj
def publish(config: Config, activity: Optional[str]):
    """Submit unpublished worklog entries to JIRA."""

    api = Api(config)

    async def publish(activity: Optional[str]):
        with transact(WORKLOG_JSON_PATH) as worklog:
            if activity is None:
                errors = await api.publish_worklog(worklog)
            else:
                errors: list[ApiError] = []

                async def publish_activity(a: Optional[Activity]):
                    nonlocal errors
                    published_activity, errors = await api.publish_activity(
                        activity, Activity.verify(a)
                    )
                    return published_activity

                await worklog.async_update_activity(activity, publish_activity)

        for e in errors:
            report_error(e)

    asyncio.run(publish(activity))
