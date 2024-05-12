import asyncio
import datetime
from itertools import groupby
import sys
from pathlib import Path
from typing import Optional

import click
from click_help_colors import HelpColorsGroup
from rich.console import Console
from rich.padding import Padding
from rich.style import Style
from rich.table import Table

from timetracker.api import Api, ApiError
from timetracker.config import Config
from timetracker.tables import (
    activity_table,
    current_stint_status_table,
    day_table,
    month_table,
    top_n_activities_status_table,
    unpublished_activities_status_table,
)
from timetracker.time import work_timedelta_str
from timetracker.worklog.data import Activity
from timetracker.worklog.io import read_from_file, transact

ERROR = click.style("\nerror:", fg="red", bold=True)
CAUSED_BY = click.style("  caused by:", bold=True)
NOTE = click.style("       note:", bold=True)


@click.group(
    cls=HelpColorsGroup,
    help_headers_color="yellow",
    help_options_color="green",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--config-file", type=click.Path(path_type=Path))
@click.pass_context
def cli(ctx: click.Context, config_file: Optional[Path]):
    if config_file is None:
        config_file = Path("~/.config/timetracker.json").expanduser()

    try:
        with open(config_file, "r") as config_stream:
            ctx.obj = Config.from_json(config_stream.read())
    except FileNotFoundError:
        click.secho(
            f"The configuration file '{click.format_filename(config_file)}' does not exist.",
            fg="yellow",
            bold=True,
        )
        if not click.confirm("Do you want to create it?"):
            raise

        if config_file.suffix != ".json":
            click.confirm(
                "Configuration file does not have '.json' extension. Proceed anyway?",
                abort=True,
            )

        store_dir: Path = click.prompt(
            "  → Storage directory location",
            type=Path,
            default=Path("~/.local/share/timetracker"),
        ).expanduser()

        if not store_dir.exists() and click.confirm(
            f"Directory '{click.format_filename(store_dir)}' does not exist. Create it?"
        ):
            store_dir.mkdir(parents=True, exist_ok=True)

        config = Config(
            store_dir=str(store_dir),
            host=click.prompt("  → JIRA API host name"),
            token=click.prompt("  → JIRA API personal access token"),
            default_group=click.prompt("  → Worklog visibility group"),
        )

        config_file.parent.mkdir(exist_ok=True)

        with open(config_file, "w") as config_stream:
            ctx.obj = config
            config_stream.write(config.to_json(indent=2))
        click.secho("✨ Configuration file has been created\n", bold=True)


@cli.command()
@click.pass_obj
def status(config: Config):
    """Print a summary of the current state of your worklog."""
    try:
        worklog = read_from_file(config.worklog_path)
    except FileNotFoundError:
        click.echo(
            "No worklog file has been created yet. Start an activity to create one."
        )
        return None

    console = Console()

    match list(worklog.running_activities()):
        case []:
            console.print("You don't have any ongoing activities 🏖️")
        case [(name, activity)]:
            console.print(
                Padding(
                    current_stint_status_table(
                        [(name, activity)], prefix="Current stint:"
                    ),
                    pad=(0, 1, 0, 0),
                )
            )
        case multiple_activities:
            console.print("[yellow bold]You have multiple ongoing activities:")
            console.print(
                Padding(
                    current_stint_status_table(multiple_activities, prefix="-"),
                    pad=(0, 1, 0, 4),
                )
            )

    unpublished_activities = sorted(
        filter(lambda a: a.seconds_unpublished > 0, worklog.summarize_activities()),
        key=lambda a: a.last_worked_on,
        reverse=True,
    )

    if len(unpublished_activities) > 0:
        if len(unpublished_activities) > 1:
            console.print(
                f"\n[yellow]You have {len(unpublished_activities)} activities with unpublished stints:"
            )
        else:
            console.print("\n[yellow]You have one activity with unpublished stints:")

        console.print(
            Padding(
                unpublished_activities_status_table(unpublished_activities),
                pad=(0, 1, 0, 4),
            )
        )

    total_seconds = sum(a.seconds_total for a in worklog.summarize_activities())
    all_activities = sorted(
        worklog.summarize_activities(), key=lambda a: a.last_worked_on, reverse=True
    )
    console.print(
        f"\n[dim]You have logged {work_timedelta_str(total_seconds)} in total:"
    )
    console.print(
        Padding(
            top_n_activities_status_table(all_activities),
            pad=(0, 1, 0, 4),
        )
    )


@cli.command()
@click.option("-t", "--today", is_flag=True)
@click.option("-w", "--this-week", is_flag=True)
@click.option("-m", "--this-month", is_flag=True)
@click.option("-y", "--this-year", is_flag=True)
@click.pass_obj
def log(
    config: Config, today: bool, this_week: bool, this_month: bool, this_year: bool
):
    """Print all worklog entries, grouped by activities, date, or issue."""

    try:
        worklog = read_from_file(config.worklog_path)
    except FileNotFoundError:
        click.echo(
            "No worklog file has been created yet. Start an activity to create one."
        )
        return None

    console = Console()

    today_date = datetime.date.today()

    if today:
        day_records = filter(
            lambda r: r.stint.begin.date() == today_date, worklog.records()
        )
        table = day_table(today_date, list(day_records))
        _apply_table_style(table)
        console.print(Padding(table, pad=1))
    elif this_week:
        week_num = today_date.isocalendar().week
        week_records = filter(
            lambda r: r.stint.begin.year == today_date.year
            and r.stint.begin.isocalendar().week == week_num,
            worklog.records(),
        )
        week_records = sorted(week_records, key=lambda r: r.stint.begin.date())
        day_groups = groupby(week_records, key=lambda r: r.stint.begin.date())
        for date, day_records in day_groups:
            table = day_table(date, list(day_records))
            _apply_table_style(table)
            console.print(Padding(table, pad=1))
    elif this_month:
        month_records = filter(
            lambda r: r.stint.begin.year == today_date.year
            and r.stint.begin.month == today_date.month,
            worklog.records(),
        )
        table = month_table(today_date, list(month_records))
        _apply_table_style(table)
        console.print(Padding(table, pad=1))
    elif this_year:
        year_records = filter(
            lambda r: r.stint.begin.year == today_date.year, worklog.records()
        )
        year_records = sorted(year_records, key=lambda r: r.stint.begin.month)
        month_groups = groupby(year_records, key=lambda r: r.stint.begin.month)
        for month, month_records in month_groups:
            table = month_table(
                datetime.date(year=today_date.year, month=month, day=1),
                list(month_records),
            )
            _apply_table_style(table)
            console.print(Padding(table, pad=1))
    else:
        for name, activity in worklog.activities.items():
            table = activity_table(name, activity)
            _apply_table_style(table)
            console.print(Padding(table, pad=1))


@cli.command()
@click.argument("activity")
@click.pass_obj
def start(config: Config, activity: str):
    """Start a new activity or resume an existing one."""
    with transact(config.worklog_path) as worklog:
        worklog.update_activity(activity, lambda a: _ensure_activity(a).started())


@cli.command()
@click.argument("activity")
@click.pass_obj
def stop(config: Config, activity: str):
    """Stop a running activity."""
    with transact(config.worklog_path) as worklog:
        worklog.update_activity(activity, lambda a: Activity.verify(a).stopped())


@cli.command()
@click.pass_obj
def reset(config: Config):
    """Delete the worklog."""
    if click.confirm("This will delete the worklog. Proceed?"):
        config.worklog_path.unlink()


@cli.command()
@click.option("--activity")
@click.pass_obj
def publish(config: Config, activity: Optional[str]):
    """Submit unpublished worklog entries to JIRA."""

    api = Api(config)

    async def publish(activity: Optional[str]):
        with transact(config.worklog_path) as worklog:
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
            _report_error(e)

    asyncio.run(publish(activity))


def cli_with_error_reporting():
    try:
        cli()
    except Exception as e:
        _report_error(e)
        sys.exit(1)


def _report_error(e: Exception):
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


def _ensure_activity(maybe_activity: Optional[Activity]) -> Activity:
    match maybe_activity:
        case None:
            return Activity(
                description=click.prompt("Description"),
                issue=click.prompt("Issue"),
            )
        case Activity():
            return maybe_activity


def _apply_table_style(table: Table):
    table.style = Style(dim=True)
    table.title_style = Style(bold=True)
    table.min_width = 50
