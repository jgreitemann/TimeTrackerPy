import datetime
from itertools import dropwhile, groupby, repeat, zip_longest
from typing import Iterable, Sequence
from rich.markup import escape
from rich.style import Style
from rich.table import Table
from timetracker.worklog.data import Activity, Record, Stint


def activity_table(name: str, activity: Activity) -> Table:
    total_seconds = sum(stint.seconds() for stint in activity.stints)

    table = Table(
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
            table.add_row(date_field, *_stint_fields(stint), style=_row_style((stint,)))

    return table


def day_table(date: datetime.date, records: Sequence[Record]) -> Table:
    total_seconds = sum(record.stint.seconds() for record in records)

    table = Table(
        title=escape(date.strftime("%A, %B %d, %Y")),
        caption=f"logged {_work_timedelta_str(total_seconds)}",
    )
    table.add_column("Activity")
    table.add_column("Issue")
    table.add_column("Begin", justify="center")
    table.add_column("End", justify="center")
    table.add_column("Duration", justify="right")

    activity_groups = (
        (activity_fields, list(records))
        for activity_fields, records in groupby(
            records, key=lambda r: (r.title, r.issue)
        )
    )
    activity_groups = sorted(activity_groups, key=lambda g: g[1][0].stint.begin)
    for activity_fields, records in activity_groups:
        table.add_section()
        for activity_fields, record in zip_longest(repeat(activity_fields, 1), records):
            table.add_row(
                *(activity_fields if activity_fields is not None else ("", "")),
                *_stint_fields(record.stint),
                style=_row_style((record.stint,)),
            )

    return table


def month_table(date: datetime.date, records: Sequence[Record]) -> Table:
    total_seconds = sum(record.stint.seconds() for record in records)

    table = Table(
        title=escape(date.strftime("%B %Y")),
        caption=f"logged {_work_timedelta_str(total_seconds)}",
    )
    table.add_column("Date")
    table.add_column("Activity")
    table.add_column("Issue")
    table.add_column("Duration", justify="right")

    for date, date_records in groupby(
        sorted(records, key=lambda r: r.stint.begin.date()),
        key=lambda r: r.stint.begin.date(),
    ):
        table.add_section()
        activity_groups = (
            (activity_fields, list(activity_records))
            for activity_fields, activity_records in groupby(
                date_records, key=lambda r: (r.title, r.issue)
            )
        )
        activity_groups = sorted(activity_groups, key=lambda g: g[1][0].stint.begin)
        for date_field, (activity_fields, activity_records) in zip_longest(
            repeat(_short_date_str(date), 1), activity_groups
        ):
            activity_seconds = sum(
                record.stint.seconds() for record in activity_records
            )
            table.add_row(
                date_field,
                *activity_fields,
                _work_timedelta_str(activity_seconds, aligned=True),
                style=_row_style((r.stint for r in activity_records)),
            )

    return table


def _stint_fields(stint: Stint) -> tuple[str, str, str]:
    return (
        _short_time_str(stint.begin.time()),
        (
            "[red bold]ongoing"
            if stint.end is None
            else _short_time_str(stint.end.time())
        ),
        _work_timedelta_str(stint.seconds(), aligned=True),
    )


def _row_style(stints: Iterable[Stint]) -> Style:
    return Style(
        color="yellow" if any(not stint.is_published for stint in stints) else None,
        bold=any(not stint.is_finished() for stint in stints),
    )


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
