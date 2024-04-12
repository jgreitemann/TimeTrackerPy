import sys
from pathlib import Path

import click
from click_help_colors import HelpColorsGroup

from timetracker.worklog.transaction import transact

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
    with transact(Path("~/Desktop/worklog.json").expanduser()) as worklog:
        click.echo(worklog)


@cli.command()
@click.argument("activity")
def start(activity: str):
    """Start a new activity or resume an existing one."""
    with transact(Path("~/Desktop/worklog.json").expanduser()) as worklog:
        worklog.update_activity(activity, lambda a: a.started())


@cli.command()
@click.argument("activity")
def stop(activity: str):
    """Stop a running activity."""
    with transact(Path("~/Desktop/worklog.json").expanduser()) as worklog:
        worklog.update_activity(activity, lambda a: a.stopped())
