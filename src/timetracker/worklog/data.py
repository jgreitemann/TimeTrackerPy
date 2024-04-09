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
    begin: datetime
    end: Optional[datetime] = None

    def __str__(self) -> str:
        finish_format = self.end.isoformat() if self.end else "now"
        return f"{self.begin.isoformat()} - {finish_format}"

    def __repr__(self) -> str:
        finish_format = self.end.isoformat() if self.end else "None"
        return f"Stint(begin={self.begin.isoformat()}, end={finish_format})"

    def is_finished(self) -> bool:
        return self.end is not None

    def finished(self) -> Self:
        if self.end is None:
            return replace(self, end=datetime.now())
        else:
            raise ActivityAlreadyStopped(self.end)


@dataclass(frozen=True)
class Activity(DataClassJsonMixin):
    stints: Sequence[Stint] = field(
        default_factory=lambda: [],
        metadata=config(**seq_coder(Stint)),
    )

    def __str__(self) -> str:
        return "\n".join(map(str, self.stints))

    def current(self) -> Optional[Stint]:
        if len(self.stints) > 0:
            return self.stints[-1]
        else:
            return None

    def started(self) -> Self:
        if (c := self.current()) and not c.is_finished():
            raise ActivityAlreadyStarted(c.begin)
        return replace(
            self,
            stints=[
                *self.stints,
                Stint(begin=datetime.now()),
            ],
        )

    def stopped(self) -> Self:
        if (c := self.current()) is None:
            raise ActivityNeverStarted()
        else:
            return replace(self, stints=[*self.stints[:-1], c.finished()])

    def is_running(self) -> bool:
        return (c := self.current()) is not None and not c.is_finished()


@dataclass
class Worklog(DataClassJsonMixin):
    activities: Mapping[str, Activity] = field(
        default_factory=lambda: {},
        metadata=config(**mapping_coder(Activity)),
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
            self.activities = {
                **self.activities,
                name: func(self.activities.get(name, Activity())),
            }
        except ActivityStateError as e:
            raise ActivityUpdateError(name) from e
