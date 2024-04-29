import datetime
from itertools import dropwhile, groupby, repeat, zip_longest
from rich.markup import escape
from rich.style import Style
from rich.table import Table
from timetracker.worklog.data import Activity


def activity_table(name: str, activity: Activity) -> Table:
    total_seconds = sum(
        (stint if stint.is_finished() else stint.finished()).seconds()
        for stint in activity.stints
    )

    table = _styled_table(
        title=escape(f"[{name}] {activity.description}"),
        caption=escape(
            f"logged {_work_timedelta_str(total_seconds)} on issue {activity.issue}"
        ),
    )

    table.add_column("Date")
    table.add_column("Begin", justify="center")
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

    return table


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


def _styled_table(*, title: str, caption: str):
    return Table(
        title=title,
        caption=caption,
        style=Style(dim=True),
        title_style=Style(bold=True),
        min_width=50,
    )
