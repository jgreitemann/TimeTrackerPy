import asyncio
from dataclasses import replace
import datetime
import subprocess
import sys
from itertools import groupby
from pathlib import Path
from typing import Iterable, Optional

import click
from click.shell_completion import CompletionItem
from click_help_colors import HelpColorsGroup
from rich.console import Console
from rich.padding import Padding
from rich.style import Style
from rich.table import Table

from timetracker.api import Api, ApiError, IssueNotFoundError
from timetracker.config import Config, data_dir
from timetracker.tables import (
    activity_table,
    current_stint_status_table,
    day_table,
    month_table,
    top_n_activities_status_table,
    unpublished_activities_status_table,
)
from timetracker.time import parse_datetime, short_datetime_str, work_timedelta_str
from timetracker.worklog.data import Activity, ActivitySummary, Worklog
from timetracker.worklog.error import AmbiguousRunningActivity
from timetracker.worklog.io import read_from_file, transact

ERROR = click.style("\nerror:", fg="red", bold=True)
CAUSED_BY = click.style("  caused by:", bold=True)
NOTE = click.style("       note:", bold=True)
WARNING = click.style("\nwarning:", fg="yellow", bold=True)


class ActivityNameType(click.ParamType):
    name: str = "activity"

    def _read_worklog(self, ctx: click.Context) -> Worklog:
        if (pctx := ctx.parent) is not None and pctx.params.get(
            "config_file"
        ) is not None:
            config_file = pctx.params["config_file"].expanduser()
        else:
            config_file = Config().file_path

        config = Config.from_json(config_file.read_bytes())
        return read_from_file(config.worklog_path)

    def _filtered_completion_items(
        self, activities: Iterable[ActivitySummary], incomplete: str
    ) -> list[CompletionItem]:
        filtered = [
            activity
            for activity in activities
            if incomplete.lower() in activity.name.lower()
            or incomplete.lower() in activity.issue.lower()
            or incomplete.lower() in activity.description.lower()
        ]
        filtered.sort(key=lambda a: a.last_worked_on, reverse=True)
        return [
            CompletionItem(
                value=activity.name,
                help=f"{activity.description} ({activity.issue})",
            )
            for activity in filtered
        ]

    def shell_complete(
        self, ctx: click.Context, param: click.Parameter, incomplete: str
    ) -> list[CompletionItem]:
        try:
            worklog = self._read_worklog(ctx)
        except FileNotFoundError:
            return super().shell_complete(ctx, param, incomplete)

        return self._filtered_completion_items(
            worklog.summarize_activities(), incomplete
        )


class RunningActivityNameType(ActivityNameType):
    def shell_complete(
        self, ctx: click.Context, param: click.Parameter, incomplete: str
    ) -> list[CompletionItem]:
        try:
            worklog = self._read_worklog(ctx)
        except FileNotFoundError:
            return super().shell_complete(ctx, param, incomplete)

        return self._filtered_completion_items(
            (
                ActivitySummary.from_raw(name, activity)
                for name, activity in worklog.running_activities()
            ),
            incomplete,
        )


class UpdateDatetimeType(click.ParamType):
    name: str = "time or offset"

    def convert(
        self,
        value: str | datetime.datetime,
        param: Optional[click.Parameter],
        ctx: Optional[click.Context],
    ) -> datetime.datetime:
        if isinstance(value, datetime.datetime):
            return value
        try:
            return parse_datetime(value)
        except ValueError as e:
            self.fail(f"cannot parse update time: {e}", param, ctx)


update_time_option = click.option(
    "-t", "--time", type=UpdateDatetimeType(), default=lambda: datetime.datetime.now()
)


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
        config_file = Config().file_path

    try:
        ctx.obj = Config.from_file(config_file)
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

        ctx.obj = _reconfigure(Config(file_path=config_file))
        ctx.obj.write_to_file()
        click.secho("✨ Configuration file has been created\n", bold=True)


@cli.command()
@click.pass_obj
def reconfigure(config: Config):
    """Update the configuration file"""
    _reconfigure(config).write_to_file()
    click.secho("✨ Configuration file has been updated\n", bold=True)


def _reconfigure(config: Config) -> Config:
    store_dir: Path = click.prompt(
        "  → Storage directory location",
        type=Path,
        default=Path(config.store_dir),
    ).expanduser()

    if not store_dir.exists() and click.confirm(
        f"Directory '{click.format_filename(store_dir)}' does not exist. Create it?"
    ):
        store_dir.mkdir(parents=True, exist_ok=True)

    return replace(
        config,
        store_dir=str(store_dir),
        host=click.prompt("  → JIRA API host name", default=config.host),
        token=click.prompt("  → JIRA API personal access token", default=config.token),
        default_group=click.prompt(
            "  → Worklog visibility group", default=config.default_group
        ),
    )


@cli.command()
@click.pass_obj
def status(config: Config):
    """Print a summary of the current state of your worklog"""
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
    """Print all worklog entries, grouped by activities, date, or issue"""

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
@update_time_option
@click.argument("activity", type=ActivityNameType())
@click.pass_obj
def start(config: Config, activity: str, time: datetime.datetime):
    """Start a new activity or resume an existing one"""
    with transact(config.worklog_path) as worklog:
        started = worklog.update_activity(
            activity, lambda a: _ensure_activity(activity, a, config).started(time)
        )
    click.echo(
        f"Starting work on [{activity}] {started.description} at {short_datetime_str(time)}."
    )


def _single_running_activity(worklog: Worklog) -> str:
    match [name for name, _ in worklog.running_activities()]:
        case []:
            click.echo("No activities are currently running.")
            sys.exit(0)
        case [name]:
            return name
        case names:
            raise AmbiguousRunningActivity(names)


@cli.command()
@update_time_option
@click.argument("activity", type=RunningActivityNameType(), required=False)
@click.pass_obj
def stop(config: Config, activity: Optional[str], time: datetime.datetime):
    """Stop a running activity"""

    with transact(config.worklog_path) as worklog:
        if activity is None:
            activity = _single_running_activity(worklog)
        stopped = worklog.update_activity(
            activity, lambda a: Activity.verify(a).stopped(time)
        )

    unpublished_secs = sum(s.seconds() for s in stopped.stints if not s.is_published)
    click.echo(
        f"Finished work on [{activity}] {stopped.description} at {short_datetime_str(time)}."
    )
    click.echo(
        f"{work_timedelta_str(unpublished_secs)} have been logged and can be published to {stopped.issue}."
    )


@cli.command()
@click.argument("activity", type=RunningActivityNameType(), required=False)
@click.pass_obj
def cancel(config: Config, activity: Optional[str]):
    """Stop an activity and do NOT save the ongoing stint"""

    with transact(config.worklog_path) as worklog:
        if activity is None:
            activity = _single_running_activity(worklog)
        canceled = worklog.update_activity(
            activity, lambda a: Activity.verify(a).canceled()
        )

    if canceled is None:
        click.echo(f"The activity {activity} has been deleted.")
    else:
        click.echo(
            f"The current stint on [{activity}] {canceled.description} has been canceled and won't be published."
        )


@cli.command()
@click.option("-f", "--force", is_flag=True)
@click.argument("activity", type=ActivityNameType())
@click.pass_obj
def remove(config: Config, force: bool, activity: str):
    """Remove an activity from the worklog"""

    def _remove_activity(a: Activity) -> None:
        if not force and any(not stint.is_published for stint in a.stints):
            click.confirm(
                "The activity contains unpublished stints. Are you sure you want to remove it?",
                abort=True,
            )

    with transact(config.worklog_path) as worklog:
        worklog.update_activity(
            activity, lambda a: _remove_activity(Activity.verify(a))
        )

    click.echo(f"The activity {activity} has been deleted.")


@cli.command()
@update_time_option
@click.argument("activity", type=ActivityNameType())
@click.pass_obj
def switch(config: Config, activity: str, time: datetime.datetime):
    """Stop all running activities and start another"""

    with transact(config.worklog_path) as worklog:
        running_activities = dict(worklog.running_activities())
        if len(running_activities) > 1:
            click.confirm(
                "More than one activity is currently running. Are you sure you want to stop all of them?",
                abort=True,
            )

        for running_activity in running_activities.keys():
            stopped = worklog.update_activity(
                running_activity, lambda a: Activity.verify(a).stopped(time)
            )
            click.echo(f"Finished work on [{running_activity}] {stopped.description}.")

        started = worklog.update_activity(
            activity, lambda a: _ensure_activity(activity, a, config).started(time)
        )

    click.echo(
        f"Starting work on [{activity}] {started.description} at {short_datetime_str(time)}."
    )


@cli.command()
@click.option("-f", "--force", is_flag=True)
@click.pass_obj
def reset(config: Config, force: bool):
    """Delete the worklog"""
    if force or click.confirm("This will delete the worklog. Proceed?"):
        config.worklog_path.unlink()


@cli.command()
@click.argument("activity", type=ActivityNameType())
@click.pass_obj
def edit(config: Config, activity: str):
    """Modify the worklog for a specific activity"""

    def _edit_update(a: Optional[Activity]) -> Optional[Activity]:
        edit_result = click.edit(
            str(_ensure_activity(activity, a, config)), config.editor
        )
        if edit_result is None:
            click.echo(f"{WARNING} Aborted editing activity as no changes were made.")
            return a

        if edit_result.strip() == "":
            if a is not None and click.confirm(
                f"The activity '{activity}' will be deleted from the worklog. Proceed?"
            ):
                return None
            else:
                return a

        return Activity.from_str(edit_result)

    with transact(config.worklog_path) as worklog:
        worklog.update_activity(
            activity,
            _edit_update,
        )


@cli.command()
@click.option("--activity", type=ActivityNameType())
@click.pass_obj
def publish(config: Config, activity: Optional[str]):
    """Submit unpublished worklog entries to JIRA"""

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


@cli.command()
@click.option("--dir", type=Path, default=data_dir() / "fish" / "vendor_completions.d")
def install_completions(dir: Path):
    """Install shell completions"""

    res = subprocess.run(
        [
            sys.executable,
            "-c",
            "__import__('timetracker.cli').cli.cli(prog_name='track')",
        ],
        env={
            "_TRACK_COMPLETE": "fish_source",
        },
        capture_output=True,
    )

    if res.returncode != 0:
        e = RuntimeError("failed to generate shell completions")
        e.add_note(f"Process exited with code {res.returncode}:\n{res.stderr.decode()}")
        raise e

    click.confirm(
        f"Shell completions will be install in {click.format_filename(dir)}.\nProceed?",
        abort=True,
    )

    patched_completions = res.stdout.replace(
        b"complete --no-files", b"complete --keep-order --no-files"
    )

    dir.mkdir(parents=True, exist_ok=True)
    completions_file = dir / "track.fish"
    completions_file.write_bytes(patched_completions)


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


def _ensure_activity(
    name: str, maybe_activity: Optional[Activity], config: Config
) -> Activity:
    if maybe_activity is None:
        return asyncio.run(_activity_wizard(name, config))
    return maybe_activity


async def _activity_wizard(name: str, config: Config) -> Activity:
    api = Api(config)

    async def prompt_issue() -> str:
        issue = click.prompt("Enter the JIRA issue key to log work on", type=str)
        try:
            await api.get_issue(issue)
            return issue
        except IssueNotFoundError:
            click.echo("There isn't a JIRA issue with that key. Please try again.")
            return await prompt_issue()

    try:
        activity_info = await api.get_issue(name)
        if click.confirm(
            f"Use '{activity_info.summary}' as activity description?", default=True
        ):
            description = activity_info.summary
        else:
            description = click.edit(activity_info.summary, config.editor)
            if description is None:
                description = activity_info.summary

        if activity_info.epic_key is None:
            click.echo("This activity is not associated with an epic.")
            if click.confirm(
                f"Do you want to log work on {name} directly?", default=True
            ):
                issue = name
            else:
                issue = await prompt_issue()
        else:
            epic_info = await api.get_issue(activity_info.epic_key)
            click.echo(
                f"This activity is associated with the epic [{epic_info.key}] {epic_info.summary}."
            )
            if click.confirm(
                f"Do you want to log work on {epic_info.key}?", default=True
            ):
                issue = epic_info.key
            else:
                issue = await prompt_issue()

    except IssueNotFoundError:
        click.echo("There isn't a JIRA issue with that key.")
        description = click.prompt("Enter a description for this activity", type=str)
        issue = await prompt_issue()

    return Activity(
        description=description,
        issue=issue,
    )


def _apply_table_style(table: Table):
    table.style = Style(dim=True)
    table.title_style = Style(bold=True)
    table.min_width = 50
