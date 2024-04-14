from io import TextIOWrapper
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from timetracker.worklog.data import Worklog


def read_from_file(path: Path) -> Worklog:
    with open(path, "r") as file:
        return Worklog.from_stream(file)


@contextmanager
def _open_rw(path: Path) -> Generator[tuple[bool, TextIOWrapper], None, None]:
    try:
        with open(path, "r+") as file:
            yield (False, file)
    except FileNotFoundError:
        with open(path, "w") as file:
            yield (True, file)


@contextmanager
def transact(path: Path) -> Generator[Worklog, None, None]:
    with _open_rw(path) as (is_new, file):
        if is_new:
            worklog = Worklog()
            original_activities = None
        else:
            worklog = Worklog.from_stream(file)
            file.seek(0)
            original_activities = worklog.activities

        yield worklog

        if worklog.activities is not original_activities:
            worklog.write_to_stream(file)
