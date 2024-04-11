from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from timetracker.worklog.data import Worklog


@contextmanager
def transact(path: Path) -> Generator[Worklog, None, None]:
    try:
        worklog = Worklog.from_file(path)
        original_activities = worklog.activities
    except FileNotFoundError:
        worklog = Worklog()
        original_activities = None

    yield worklog

    if worklog.activities is not original_activities:
        worklog.write_to_file(path)
