import datetime
from itertools import groupby, islice, repeat, zip_longest
from typing import Iterable, Sequence

from rich.markup import escape
from rich.style import Style
from rich.table import Table

from timetracker.time import short_date_str, short_time_str, work_timedelta_str
from timetracker.worklog.data import Activity, ActivitySummary, Record, Stint
from timetracker.worklog.error import ActivityAlreadyStopped, ActivityNeverStarted


def activity_table(name: str, activity: Activity) -> Table:
    total_seconds = sum(stint.seconds() for stint in activity.stints)

    table = Table(
        title=escape(f"[{name}] {activity.description}"),
        caption=escape(
            f"logged {work_timedelta_str(total_seconds)} on issue {activity.issue}"
        ),
    )

    table.add_column("Date")
    table.add_column("Begin", justify="center")
    table.add_column("End", justify="center")
    table.add_column("Duration", justify="right")

    for date_field, stints in groupby(
        activity.stints, key=lambda s: short_date_str(s.begin.date())
    ):
        table.add_section()
        for date_field, stint in zip_longest(repeat(date_field, 1), stints):
            table.add_row(date_field, *_stint_fields(stint), style=_row_style((stint,)))

    return table


def day_table(date: datetime.date, records: Sequence[Record]) -> Table:
    total_seconds = sum(record.stint.seconds() for record in records)

    table = Table(
        title=escape(date.strftime("%A, %B %d, %Y")),
        caption=f"logged {work_timedelta_str(total_seconds)}",
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
        caption=f"logged {work_timedelta_str(total_seconds)}",
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
            repeat(short_date_str(date), 1), activity_groups
        ):
            activity_seconds = sum(
                record.stint.seconds() for record in activity_records
            )
            table.add_row(
                date_field,
                *activity_fields,
                work_timedelta_str(activity_seconds, aligned=True),
                style=_row_style((r.stint for r in activity_records)),
            )

    return table


def current_stint_status_table(
    activities: Iterable[tuple[str, Activity]], prefix: str = ""
) -> Table:
    table = Table.grid(expand=True, padding=1)
    table.add_column()
    table.add_column(style="red")
    table.add_column(ratio=10)
    table.add_column(style="yellow bold", justify="right")

    for name, activity in activities:
        ongoing_stint = activity.current()
        if ongoing_stint is None:
            raise ActivityNeverStarted()
        if ongoing_stint.end is not None:
            raise ActivityAlreadyStopped(ongoing_stint.end)

        table.add_row(
            prefix,
            escape(f"[{name}]"),
            escape(activity.description),
            work_timedelta_str(ongoing_stint.seconds(), aligned=True),
        )

    return table


def unpublished_activities_status_table(
    unpublished_activities: Iterable[ActivitySummary],
) -> Table:
    table = Table.grid(expand=True, padding=(0, 1))
    table.add_column()
    table.add_column(ratio=10, no_wrap=True)
    table.add_column(style="yellow", justify="right")
    table.add_column()

    for summary in unpublished_activities:
        table.add_row(
            escape(f"[{summary.name}]"),
            escape(summary.description),
            work_timedelta_str(summary.seconds_unpublished, aligned=True),
            f"({summary.stints_unpublished} stints)",
        )

    return table


def top_n_activities_status_table(
    activities: Iterable[ActivitySummary], n: int = 3
) -> Table:
    table = Table.grid(expand=True, padding=(0, 1))
    table.add_column()
    table.add_column(ratio=10, no_wrap=True)
    table.add_column(justify="right")

    activities_iter = iter(activities)
    for summary in islice(activities_iter, n):
        table.add_row(
            escape(f"[{summary.name}]"),
            escape(summary.description),
            work_timedelta_str(summary.seconds_total, aligned=True),
        )

    if remaining := sum(1 for _ in activities_iter):
        if remaining == 1:
            table.caption = "...and one more activity"
        else:
            table.caption = f"...and {remaining} more activities"
        table.caption_justify = "left"
        table.caption_style = "dim"

    return table


def _stint_fields(stint: Stint) -> tuple[str, str, str]:
    return (
        short_time_str(stint.begin.time()),
        (
            "[red bold]ongoing"
            if stint.end is None
            else short_time_str(stint.end.time())
        ),
        work_timedelta_str(stint.seconds(), aligned=True),
    )


def _row_style(stints: Iterable[Stint]) -> Style:
    return Style(
        color="yellow" if any(not stint.is_published for stint in stints) else None,
        bold=any(not stint.is_finished() for stint in stints),
    )
