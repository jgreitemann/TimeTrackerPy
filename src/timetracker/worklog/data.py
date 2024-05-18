from dataclasses import dataclass, field, replace
from datetime import datetime
from io import IOBase
from typing import (
    Awaitable,
    Callable,
    Iterable,
    Mapping,
    Optional,
    Self,
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
    WorklogDeserializationError,
)
from timetracker.worklog.coder import mapping_coder


@dataclass(frozen=True, order=True)
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

    def begin_jira_format(self) -> str:
        return self.begin.strftime("%Y-%m-%dT%H:%M:%S.000%z")

    def seconds(self) -> int:
        if self.end is None:
            return self.finished().seconds()
        else:
            return round((self.end - self.begin).total_seconds())


@dataclass(frozen=True)
class Activity(DataClassJsonMixin):
    description: str
    issue: str
    stints: tuple[Stint, ...] = field(default_factory=tuple)

    def __post_init__(self):
        sorted_stints = tuple(sorted(self.stints))
        if sorted_stints != self.stints:
            object.__setattr__(self, "stints", tuple(sorted(self.stints)))

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
            stints=(
                *self.stints,
                Stint(begin=datetime.now().astimezone()),
            ),
        )

    def stopped(self) -> Self:
        if (c := self.current()) is None:
            raise ActivityNeverStarted()
        else:
            return replace(self, stints=(*self.stints[:-1], c.finished()))

    def is_running(self) -> bool:
        return (c := self.current()) is not None and not c.is_finished()

    @staticmethod
    def verify(maybe_activity: Optional["Activity"]) -> "Activity":
        match maybe_activity:
            case None:
                raise ActivityNotFound()
            case Activity():
                return maybe_activity


@dataclass(frozen=True)
class Record:
    title: str
    issue: str
    stint: Stint


@dataclass(frozen=True)
class ActivitySummary:
    name: str
    description: str
    seconds_total: int
    seconds_unpublished: int
    stints_unpublished: int
    last_worked_on: datetime


@dataclass
class Worklog(DataClassJsonMixin):
    activities: Mapping[str, Activity] = field(
        default_factory=lambda: {},
        metadata=config(**mapping_coder(Activity)),
    )

    @classmethod
    def from_stream(cls, input_stream: IOBase) -> Self:
        try:
            return cls.from_json(input_stream.read())
        except Exception as e:
            raise WorklogDeserializationError() from e

    def write_to_stream(self, output_stream: IOBase):
        output_stream.write(self.to_json(indent=2))

    def __str__(self) -> str:
        return "\n\n".join(
            f"{name}\n------------\n{activity}"
            for name, activity in self.activities.items()
        )

    def records(self) -> Iterable[Record]:
        for name, activity in self.activities.items():
            title = f"[{name}] {activity.description}"
            for stint in activity.stints:
                yield Record(title, activity.issue, stint)

    def summarize_activities(self) -> Iterable[ActivitySummary]:
        return (
            ActivitySummary(
                name,
                activity.description,
                seconds_total=sum(s.seconds() for s in activity.stints),
                seconds_unpublished=sum(
                    s.seconds() for s in activity.stints if not s.is_published
                ),
                stints_unpublished=sum(
                    1 for s in activity.stints if not s.is_published
                ),
                last_worked_on=activity.stints[-1].begin,
            )
            for name, activity in self.activities.items()
            if len(activity.stints) > 0
        )

    def running_activities(self) -> Iterable[tuple[str, Activity]]:
        return (
            (name, activity)
            for (name, activity) in self.activities.items()
            if activity.is_running()
        )

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

    async def async_update_activity(
        self, name: str, func: Callable[[Optional[Activity]], Awaitable[Activity]]
    ):
        try:
            self.activities = {
                **self.activities,
                name: await func(self.activities.get(name)),
            }
        except ActivityStateError as e:
            raise ActivityUpdateError(name) from e
