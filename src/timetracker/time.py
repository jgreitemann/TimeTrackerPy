import datetime
import re
from itertools import dropwhile


def short_date_str(
    date: datetime.date, relative_to: datetime.date = datetime.date.today()
) -> str:
    if date == relative_to:
        return "Today"
    elif date.year == relative_to.year:
        return f"{date:%a %b %d}"
    else:
        return f"{date:%a %b %d %Y}"


def short_time_str(time: datetime.time) -> str:
    return time.isoformat(timespec="minutes")


def short_datetime_str(
    time: datetime.datetime, relative_to: datetime.date = datetime.date.today()
) -> str:
    time = time.astimezone()
    if time.date() == relative_to:
        return short_time_str(time.time())
    else:
        return f"{short_date_str(time.date())}, {short_time_str(time.time())}"


def work_timedelta_str(seconds: int, aligned: bool = False) -> str:
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


def parse_datetime(
    datetime_str: str,
    relative_to: datetime.datetime = datetime.datetime.now().astimezone(),
) -> datetime.datetime:
    if len(datetime_str) > 1 and (
        m := re.match(
            r"^([+-])(?:(\d+)w\s?)?(?:(\d+)d\s?)?(?:(\d+)h\s?)?(?:(\d+)m\s?)?$",
            datetime_str,
        )
    ):

        def unpack(x: str | None):
            return 0 if x is None else int(x)

        delta = datetime.timedelta(
            weeks=unpack(m.group(2)),
            days=unpack(m.group(3)),
            hours=unpack(m.group(4)),
            minutes=unpack(m.group(5)),
        )
        if m.group(1) == "-":
            return relative_to - delta
        else:
            return relative_to + delta

    try:
        return datetime.datetime.fromisoformat(datetime_str)
    except ValueError:
        time = datetime.time.fromisoformat(datetime_str)
        return datetime.datetime.combine(
            relative_to.astimezone(time.tzinfo).date(), time
        )
