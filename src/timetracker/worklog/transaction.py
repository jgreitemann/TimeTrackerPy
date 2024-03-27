from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from timetracker.worklog.data import Worklog


@contextmanager
def transact(path: Path) -> Generator[Worklog, None, None]:
    worklog = Worklog.from_file(path)
    yield worklog
    worklog.write_to_file(path)
