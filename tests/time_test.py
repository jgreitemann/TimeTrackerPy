from datetime import UTC, date, datetime, timedelta, timezone, time
from ward import test

from timetracker.time import parse_datetime


@test("Full ISO format can be parsed")
def _():
    assert parse_datetime("2024-06-16T12:34:56Z") == datetime(
        year=2024, month=6, day=16, hour=12, minute=34, second=56, tzinfo=UTC
    )
    assert parse_datetime("2024-06-16T12:34:56+02:00") == datetime(
        year=2024,
        month=6,
        day=16,
        hour=12,
        minute=34,
        second=56,
        tzinfo=timezone(offset=timedelta(hours=2)),
    )


@test("ISO format without timezone is parsed as naive datetime")
def _():
    assert parse_datetime("2024-06-16T12:34:56") == datetime(
        year=2024,
        month=6,
        day=16,
        hour=12,
        minute=34,
        second=56,
    )


@test("Variations on ISO format can also be parsed")
def _():
    expected = parse_datetime("2024-06-16T12:34:56")
    assert parse_datetime("20240616T123456") == expected
    assert parse_datetime("2024-06-16 12:34:56") == expected
    assert parse_datetime("2024-06-16?12:34:56") == expected


@test("Times without date are parsed relative to today's date")
def _():
    assert parse_datetime("12:34:56") == datetime.combine(
        date.today(), time(hour=12, minute=34, second=56)
    )
    assert parse_datetime(
        "12:34:56", relative_to=datetime(year=2024, month=6, day=16)
    ) == parse_datetime("2024-06-16T12:34:56")


@test("Relative times can be parsed")
def _():
    NOW = datetime.now().astimezone()
    assert parse_datetime("-15m", NOW) - NOW == timedelta(minutes=-15)
    assert parse_datetime("-5d", NOW) - NOW == timedelta(days=-5)
    assert parse_datetime("-1h 20m", NOW) - NOW == timedelta(hours=-1, minutes=-20)
    assert parse_datetime("-1w 2d 3h 4m", NOW) - NOW == timedelta(
        weeks=-1, days=-2, hours=-3, minutes=-4
    )
    assert parse_datetime("-1w2d3h4m", NOW) - NOW == timedelta(
        weeks=-1, days=-2, hours=-3, minutes=-4
    )
    assert parse_datetime("-1w4m", NOW) - NOW == timedelta(weeks=-1, minutes=-4)
    assert parse_datetime("+1w 2d 3h 4m", NOW) - NOW == timedelta(
        weeks=1, days=2, hours=3, minutes=4
    )
