import click

from pathlib import Path

from timetracker.worklog.transaction import transact


@click.group()
def cli():
    pass


@cli.command()
def status():
    with transact(Path("~/Desktop/worklog.json").expanduser()) as worklog:
        print(worklog)


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
