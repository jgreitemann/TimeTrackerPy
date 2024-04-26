import asyncio
import datetime
from itertools import dropwhile, groupby, repeat, zip_longest
import sys
from pathlib import Path
from typing import Optional

import click
from click_help_colors import HelpColorsGroup
from rich.console import Console
from rich.padding import Padding
from rich.style import Style
from rich.table import Table
from rich.markup import escape

from timetracker.api import Api, ApiError
from timetracker.config import Config
from timetracker.worklog.data import Activity
from timetracker.worklog.io import read_from_file, transact

ERROR = click.style("\nerror:", fg="red", bold=True)
CAUSED_BY = click.style("  caused by:", bold=True)
NOTE = click.style("       note:", bold=True)


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


def ensure_activity(maybe_activity: Optional[Activity]) -> Activity:
    match maybe_activity:
        case None:
            return Activity(
                description=click.prompt("Description"),
                issue=click.prompt("Issue"),
            )
        case Activity():
            return maybe_activity


def _short_date_str(
    date: datetime.date, relative_to: datetime.date = datetime.date.today()
) -> str:
    if date == relative_to:
        return "Today"
    elif date.year == relative_to.year:
        return f"{date:%a %b %d}"
    else:
        return f"{date:%a %b %d %Y}"


def _short_time_str(time: datetime.time) -> str:
    return time.isoformat(timespec="minutes")


def _work_timedelta_str(seconds: int, aligned: bool = False) -> str:
    weeks, seconds = divmod(seconds, 144000)
    days, seconds = divmod(seconds, 28800)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if aligned:
        components = [
            f"{weeks}w",
            f"{days}d",
            f"{hours:2}h",
            f"{minutes:2}m",
        ]
    else:
        components = [
            f"{weeks}w",
            f"{days}d",
            f"{hours}h",
            f"{minutes}m",
        ]

    components = list(dropwhile(lambda s: s.lstrip().startswith("0"), components))

    if len(components) == 0:
        return f"{seconds}s"

    return " ".join(components)


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
    """Print a summary of the worklog by activity."""
    try:
        worklog = read_from_file(config.worklog_path)
        click.echo(worklog)
    except FileNotFoundError:
        click.echo(
            "No worklog file has been created yet. Start an activity to create one."
        )


@cli.command()
@click.pass_obj
def log(config: Config):
    """Print all worklog entries, grouped by activities, date, or issue."""

    try:
        worklog = read_from_file(config.worklog_path)
    except FileNotFoundError:
        click.echo(
            "No worklog file has been created yet. Start an activity to create one."
        )
        return None

    console = Console()

    for name, activity in worklog.activities.items():
        total_seconds = sum(
            (stint if stint.is_finished() else stint.finished()).seconds()
            for stint in activity.stints
        )

        table = Table(
            title=escape(f"[{name}] {activity.description}"),
            caption=escape(
                f"logged {_work_timedelta_str(total_seconds)} on issue {activity.issue}"
            ),
            title_style=Style(bold=True),
            style=Style(dim=True),
            min_width=50,
        )

        table.add_column("Date")
        table.add_column("Start", justify="center")
        table.add_column("End", justify="center")
        table.add_column("Duration", justify="right")

        for date_field, stints in groupby(
            activity.stints, key=lambda s: _short_date_str(s.begin.date())
        ):
            table.add_section()
            for date_field, stint in zip_longest(repeat(date_field, 1), stints):
                table.add_row(
                    date_field,
                    _short_time_str(stint.begin.time()),
                    (
                        "[red bold]ongoing"
                        if stint.end is None
                        else _short_time_str(stint.end.time())
                    ),
                    _work_timedelta_str(
                        (stint if stint.is_finished() else stint.finished()).seconds(),
                        aligned=True,
                    ),
                    style=Style(
                        color=None if stint.is_published else "yellow",
                        bold=not stint.is_finished(),
                    ),
                )

        console.print(Padding(table, pad=1))


@cli.command()
@click.argument("activity")
@click.pass_obj
def start(config: Config, activity: str):
    """Start a new activity or resume an existing one."""
    with transact(config.worklog_path) as worklog:
        worklog.update_activity(activity, lambda a: ensure_activity(a).started())


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
            report_error(e)

    asyncio.run(publish(activity))
