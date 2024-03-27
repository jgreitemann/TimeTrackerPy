from dataclasses import dataclass
from dataclasses_json import DataClassJsonMixin
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Self


@dataclass
class Interval(DataClassJsonMixin):
    start: datetime
    finish: Optional[datetime]

    def __str__(self) -> str:
        finish_format = self.finish.isoformat() if self.finish else "now"
        return f"{self.start.isoformat()} - {finish_format}"


class ActivityStateError(Exception):
    def __init__(self, conflicting_interval: Optional[Interval]):
        self.conflicting_interval = conflicting_interval
        if conflicting_interval is None:
            super().__init__("failed to stop activity which was never started")
        elif conflicting_interval.finish is None:
            super().__init__(
                f"failed to start activity which was already started at {conflicting_interval.start.isoformat()}"
            )
        else:
            super().__init__(
                f"failed to stop activity which was already stopped at {conflicting_interval.finish.isoformat()}"
            )


@dataclass
class Activity(DataClassJsonMixin):
    logged_work: List[Interval]

    def __str__(self) -> str:
        return "\n".join(map(str, self.logged_work))

    def current(self) -> Optional[Interval]:
        if len(self.logged_work) > 0:
            return self.logged_work[-1]
        else:
            return None

    def start(self):
        if (c := self.current()) and c.finish is None:
            raise ActivityStateError(c)
        self.logged_work.append(Interval(start=datetime.now(), finish=None))

    def finish(self):
        if (c := self.current()) is None or c.finish is not None:
            raise ActivityStateError(c)
        else:
            c.finish = datetime.now()


@dataclass
class Worklog(DataClassJsonMixin):
    activities: Dict[str, Activity]

    def __str__(self) -> str:
        return "\n\n".join(
            f"{name}\n------------\n{activity}"
            for name, activity in self.activities.items()
        )

    @classmethod
    def from_file(cls, path: Path) -> Self:
        with open(path, "r") as file:
            return cls.from_json(file.read())

    def write_to_file(self, path: Path):
        with open(path, "w") as file:
            file.write(self.to_json())

    def activity(self, name: str) -> Activity:
        return self.activities.get(name, Activity([]))
