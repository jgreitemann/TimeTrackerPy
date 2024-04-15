import sys
from pathlib import Path
from typing import Optional

import click
from click_help_colors import HelpColorsGroup

from timetracker.worklog.data import Activity
from timetracker.worklog.io import read_from_file, transact

ERROR = click.style("error:", fg="red", bold=True)
CAUSED_BY = click.style("caused by:", bold=True)


def cli_with_error_reporting():
    try:
        cli()
    except Exception as e:
        click.echo(f"{ERROR} {e}", err=True)
        cause = e
        while (cause := cause.__cause__) is not None:
            click.echo(f"{CAUSED_BY} {cause}", err=True)
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
def cli():
    pass


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
