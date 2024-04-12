import sys
from pathlib import Path

import click

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


@click.group()
def cli():
    pass


@cli.command()
def status():
    with transact(Path("~/Desktop/worklog.json").expanduser()) as worklog:
        click.echo(worklog)


@cli.command()
@click.argument("activity")
def start(activity: str):
    with transact(Path("~/Desktop/worklog.json").expanduser()) as worklog:
        worklog.update_activity(activity, lambda a: a.started())


@cli.command()
@click.argument("activity")
def stop(activity: str):
    with transact(Path("~/Desktop/worklog.json").expanduser()) as worklog:
        worklog.update_activity(activity, lambda a: a.stopped())
