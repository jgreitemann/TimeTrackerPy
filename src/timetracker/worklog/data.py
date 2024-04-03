from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import (
    Callable,
    Mapping,
    Optional,
    Self,
    Sequence,
)

from dataclasses_json import DataClassJsonMixin, config

from timetracker.worklog.error import (
    ActivityAlreadyStarted,
    ActivityAlreadyStopped,
    ActivityNeverStarted,
    ActivityStateError,
    ActivityUpdateError,
)
from timetracker.worklog.coder import mapping_coder, seq_coder


@dataclass(frozen=True)
class Stint(DataClassJsonMixin):
    start: datetime
    finish: Optional[datetime]

    def __str__(self) -> str:
        finish_format = self.finish.isoformat() if self.finish else "now"
        return f"{self.start.isoformat()} - {finish_format}"

    def is_finished(self) -> bool:
        return self.finish is not None

    def finished(self) -> Self:
        if self.finish is None:
            return replace(self, finish=datetime.now())
        else:
            raise ActivityAlreadyStopped(self.finish)


@dataclass(frozen=True)
class Activity(DataClassJsonMixin):
    stints: Sequence[Stint] = field(metadata=config(**seq_coder(Stint)))

    def __str__(self) -> str:
        return "\n".join(map(str, self.stints))

    def current(self) -> Optional[Stint]:
        if len(self.stints) > 0:
            return self.stints[-1]
        else:
            return None

    def started(self) -> Self:
        if (c := self.current()) and not c.is_finished():
            raise ActivityAlreadyStarted(c.start)
        return replace(
            self,
            stints=[
                *self.stints,
                Stint(start=datetime.now(), finish=None),
            ],
        )

    def stopped(self) -> Self:
        if (c := self.current()) is None:
            raise ActivityNeverStarted()
        else:
            return replace(self, stints=[*self.stints[:-1], c.finished()])


@dataclass
class Worklog(DataClassJsonMixin):
    activities: Mapping[str, Activity] = field(
        metadata=config(**mapping_coder(Activity))
    )

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

    def update_activity(self, name: str, func: Callable[[Activity], Activity]):
        try:
            self.activities = {**self.activities, name: func(self.activities[name])}
        except ActivityStateError as e:
            raise ActivityUpdateError(name) from e
