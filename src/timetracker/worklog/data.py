from dataclasses import dataclass, field, replace
from datetime import datetime
from io import IOBase
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
    ActivityNotFound,
    ActivityStateError,
    ActivityUpdateError,
    StintNotFinishedError,
)
from timetracker.worklog.coder import mapping_coder, seq_coder


@dataclass(frozen=True)
class Stint(DataClassJsonMixin):
    begin: datetime
    end: Optional[datetime] = None
    is_published: bool = False

    def __str__(self) -> str:
        finish_format = self.end.isoformat() if self.end else "now"
        published_format = "" if self.is_published else " (*)"
        return f"{self.begin.isoformat()} - {finish_format}{published_format}"

    def __repr__(self) -> str:
        finish_format = self.end.isoformat() if self.end else "None"
        return f"Stint(begin={self.begin.isoformat()}, end={finish_format}, is_published={self.is_published})"

    def is_finished(self) -> bool:
        return self.end is not None

    def finished(self) -> Self:
        if self.end is None:
            return replace(self, end=datetime.now().astimezone())
        else:
            raise ActivityAlreadyStopped(self.end)

    def published(self) -> Self:
        if self.end is None:
            raise StintNotFinishedError()
        elif self.is_published:
            return self
        else:
            return replace(self, is_published=True)

    def seconds(self) -> int:
        if self.end is None:
            raise StintNotFinishedError()
        else:
            return round((self.end - self.begin).total_seconds())


@dataclass(frozen=True)
class Activity(DataClassJsonMixin):
    description: str
    issue: str
    stints: Sequence[Stint] = field(
        default_factory=lambda: [],
        metadata=config(**seq_coder(Stint)),
    )

    def __str__(self) -> str:
        return f"{self.description}\nIssue: {self.issue}\n" + "\n".join(
            map(str, self.stints)
        )

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
                Stint(begin=datetime.now().astimezone()),
            ],
        )

    def stopped(self) -> Self:
        if (c := self.current()) is None:
            raise ActivityNeverStarted()
        else:
            return replace(self, stints=[*self.stints[:-1], c.finished()])

    def is_running(self) -> bool:
        return (c := self.current()) is not None and not c.is_finished()

    @staticmethod
    def verify(maybe_activity: Optional["Activity"]) -> "Activity":
        match maybe_activity:
            case None:
                raise ActivityNotFound()
            case Activity():
                return maybe_activity


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
    def from_stream(cls, input_stream: IOBase) -> Self:
        return cls.from_json(input_stream.read())

    def write_to_stream(self, output_stream: IOBase):
        output_stream.write(self.to_json(indent=2))

    def update_activity(
        self, name: str, func: Callable[[Optional[Activity]], Activity]
    ):
        try:
            self.activities = {
                **self.activities,
                name: func(self.activities.get(name)),
            }
        except ActivityStateError as e:
            raise ActivityUpdateError(name) from e
