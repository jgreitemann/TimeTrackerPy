from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional
from rich.console import Console
from rich.table import Column, Table, box
from ward import test, fixture, using
from ward.expect import assert_equal
import re

from timetracker.tables import activity_table, day_table

from timetracker.worklog.data import Activity, Record, Stint


# "YESTERDAY" might actually be tomorrow -- if today is Jan 1.
# This is done such that the variable always designates a date other than today this year.
YESTERDAY = (
    date.today() - timedelta(days=1)
    if date.today().day != 1 or date.today().month != 1
    else date.today() + timedelta(days=1)
)

APR_1_2024 = date(2024, 4, 1)

TODAY_MORNING_STINT = Stint(
    begin=datetime.combine(date.today(), time(8, 23, 12)).astimezone(),
    end=datetime.combine(date.today(), time(11, 59, 45)).astimezone(),
)

TODAY_AFTERNOON_STINT = Stint(
    begin=datetime.combine(date.today(), time(13, 3, 18)).astimezone(),
    end=datetime.combine(date.today(), time(18, 11, 33)).astimezone(),
)

YESTERDAY_AFTERNOON_STINT = Stint(
    begin=datetime.combine(YESTERDAY, time(12, 48, 11)).astimezone(),
    end=datetime.combine(YESTERDAY, time(17, 32, 21)).astimezone(),
)

APR_1_MORNING_STINT = Stint(
    begin=datetime.combine(APR_1_2024, time(8, 23, 12)).astimezone(),
    end=datetime.combine(APR_1_2024, time(11, 59, 45)).astimezone(),
)

APR_1_AFTERNOON_STINT = Stint(
    begin=datetime.combine(APR_1_2024, time(13, 3, 18)).astimezone(),
    end=datetime.combine(APR_1_2024, time(18, 11, 33)).astimezone(),
)


@dataclass
class TablesFixture:
    expected: Table
    actual: Optional[Table] = None

    def assert_equal(self):
        assert (
            self.actual is not None
        ), "actual_table property of fixture must be initialized"
        actual_table = _render_table(self.actual)
        expected_table = _render_table(self.expected)
        if re.sub(r" +", " ", actual_table) != re.sub(r" +", " ", expected_table):
            assert_equal(
                actual_table,
                expected_table,
                "Rendered table does not match expectation",
            )


@fixture
def tables():
    return TablesFixture(expected=Table())


@test("Table for an empty activity")
@using(tables=tables)
def _(tables: TablesFixture):
    tables.actual = activity_table(
        "MVTS-1", Activity(description="Support case", issue="TIME-13", stints=[])
    )

    tables.expected.title = "[MVTS-1] Support case"
    tables.expected.caption = "logged 0s on issue TIME-13"
    tables.expected.columns = [
        Column("Date"),
        Column("Begin"),
        Column("End"),
        Column("Duration"),
    ]

    tables.assert_equal()


@test("Table for an activity with two stints on separate days")
@using(tables=tables)
def _(tables: TablesFixture):
    tables.actual = activity_table(
        "MVTS-1",
        Activity(
            description="Support case",
            issue="TIME-13",
            stints=[
                YESTERDAY_AFTERNOON_STINT,
                TODAY_MORNING_STINT,
            ],
        ),
    )

    tables.expected.title = "[MVTS-1] Support case"
    tables.expected.caption = "logged 1d 0h 20m on issue TIME-13"
    tables.expected.columns = [
        Column("Date"),
        Column("Begin"),
        Column("End"),
        Column("Duration"),
    ]
    tables.expected.add_row(_date_str(YESTERDAY), "12:48", "17:32", "4h 44m")
    tables.expected.add_section()
    tables.expected.add_row("Today", "08:23", "11:59", "3h 36m")

    tables.assert_equal()


@test("Table for an activity with two stints on the same day")
@using(tables=tables)
def _(tables: TablesFixture):
    tables.actual = activity_table(
        "MVTS-1",
        Activity(
            description="Support case",
            issue="TIME-13",
            stints=[TODAY_MORNING_STINT, TODAY_AFTERNOON_STINT],
        ),
    )

    tables.expected.title = "[MVTS-1] Support case"
    tables.expected.caption = "logged 1d 0h 44m on issue TIME-13"
    tables.expected.columns = [
        Column("Date"),
        Column("Begin"),
        Column("End"),
        Column("Duration"),
    ]
    tables.expected.add_row("Today", "08:23", "11:59", "3h 36m")
    tables.expected.add_row("", "13:03", "18:11", "5h 8m")

    tables.assert_equal()


@test("Table for an activity with an ongoing stint")
@using(tables=tables)
def _(tables: TablesFixture):
    TODAY_ONGOING_STINT = Stint(
        begin=datetime.now().astimezone() - timedelta(seconds=330),
    )

    tables.actual = activity_table(
        "MVTS-1",
        Activity(
            description="Support case",
            issue="TIME-13",
            stints=[TODAY_ONGOING_STINT],
        ),
    )

    tables.expected.title = "[MVTS-1] Support case"
    tables.expected.caption = "logged 5m on issue TIME-13"
    tables.expected.columns = [
        Column("Date"),
        Column("Begin"),
        Column("End"),
        Column("Duration"),
    ]
    tables.expected.add_row(
        "Today", TODAY_ONGOING_STINT.begin.strftime("%H:%M"), "ongoing", "5m"
    )

    tables.assert_equal()


@test("Table for a day without any stints")
@using(tables=tables)
def _(tables: TablesFixture):
    tables.actual = day_table(date=date(2024, 5, 2), records=[])

    tables.expected.title = "Thursday, May 02, 2024"
    tables.expected.caption = "logged 0s"
    tables.expected.columns = [
        Column("Activity"),
        Column("Issue"),
        Column("Begin"),
        Column("End"),
        Column("Duration"),
    ]

    tables.assert_equal()


@test("Table for a day with two stints of different activities")
@using(tables=tables)
def _(tables: TablesFixture):
    tables.actual = day_table(
        date=APR_1_2024,
        records=[
            Record(title="[Fools] Prank", issue="TIME-69", stint=APR_1_MORNING_STINT),
            Record(
                title="[ME-12345] Serious work",
                issue="TIME-8",
                stint=APR_1_AFTERNOON_STINT,
            ),
        ],
    )

    tables.expected.title = "Monday, April 01, 2024"
    tables.expected.caption = "logged 1d 0h 44m"
    tables.expected.columns = [
        Column("Activity"),
        Column("Issue"),
        Column("Begin"),
        Column("End"),
        Column("Duration"),
    ]
    tables.expected.add_row("[Fools] Prank", "TIME-69", "08:23", "11:59", "3h 36m")
    tables.expected.add_section()
    tables.expected.add_row(
        "[ME-12345] Serious work", "TIME-8", "13:03", "18:11", "5h 8m"
    )

    tables.assert_equal()


@test("Table for a day with two stints of the same activity")
@using(tables=tables)
def _(tables: TablesFixture):
    tables.actual = day_table(
        date=APR_1_2024,
        records=[
            Record(title="[Fools] Prank", issue="TIME-69", stint=APR_1_MORNING_STINT),
            Record(title="[Fools] Prank", issue="TIME-69", stint=APR_1_AFTERNOON_STINT),
        ],
    )

    tables.expected.title = "Monday, April 01, 2024"
    tables.expected.caption = "logged 1d 0h 44m"
    tables.expected.columns = [
        Column("Activity"),
        Column("Issue"),
        Column("Begin"),
        Column("End"),
        Column("Duration"),
    ]
    tables.expected.add_row("[Fools] Prank", "TIME-69", "08:23", "11:59", "3h 36m")
    tables.expected.add_row("", "", "13:03", "18:11", "5h 8m")

    tables.assert_equal()


def _render_table(table: Table):
    console = Console(width=70)
    with console.capture() as capture:
        table.box = box.ASCII_DOUBLE_HEAD
        console.print(table)
    return capture.get()


def _date_str(d: date) -> str:
    SHORT_MONTH = [date(1970, month, 1).strftime("%b") for month in range(1, 13)]
    SHORT_WEEKDAY = [date(1970, 1, day).strftime("%a") for day in range(5, 12)]
    return f"{SHORT_WEEKDAY[d.weekday()]} {SHORT_MONTH[d.month-1]} {d.day:02}"
