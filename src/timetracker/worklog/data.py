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
    ActivityRunningIntermittentStint,
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

    @classmethod
    def from_str(cls, input: str) -> Self:
        try:
            begin_str, end_str, *modifiers = input.strip().split()
            modifiers = "".join(modifiers).removeprefix("(").removesuffix(")")
            unrecognized_modifiers = list(filter(lambda m: m != "*", modifiers))
            if len(unrecognized_modifiers) > 0:
                raise ValueError(
                    f"encountered unrecognized stint modifiers: {', '.join(unrecognized_modifiers)}"
                )
            return cls(
                begin=datetime.fromisoformat(begin_str),
                end=None if end_str == "now" else datetime.fromisoformat(end_str),
                is_published="*" not in modifiers,
            )
        except Exception as e:
            raise ValueError("failed to parse stint") from e

    def __str__(self) -> str:
        finish_format = self.end.isoformat() if self.end else "now"
        published_format = "" if self.is_published else " (*)"
        return f"{self.begin.isoformat()} {finish_format}{published_format}"

    def __repr__(self) -> str:
        finish_format = self.end.isoformat() if self.end else "None"
        return f"Stint(begin={self.begin.isoformat()}, end={finish_format}, is_published={self.is_published})"

    def __contains__(self, time: datetime) -> bool:
        return self.begin <= time and (self.end is None or time <= self.end)

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
        if not all(stint.is_finished() for stint in self.stints[:-1]):
            raise ActivityRunningIntermittentStint()

    @classmethod
    def from_str(cls, input: str) -> Optional[Self]:
        try:
            header, *rest = input.strip().split("\n\n", maxsplit=1)

            description, issue_line = header.splitlines()
            if not issue_line.startswith("Issue: "):
                raise ValueError("missing 'Issue:' line")
        except Exception as e:
            raise ValueError("failed to parse activity header") from e

        return cls(
            description=description,
            issue=issue_line.removeprefix("Issue: "),
            stints=tuple(
                Stint.from_str(s)
                for stint_lines in rest
                for s in stint_lines.splitlines()
            ),
        )

    def __str__(self) -> str:
        return f"{self.description}\nIssue: {self.issue}\n\n" + "\n".join(
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

    def canceled(self) -> Optional[Self]:
        if (c := self.current()) is None:
            raise ActivityNeverStarted()
        elif c.end is not None:
            raise ActivityAlreadyStopped(c.end)
        elif len(self.stints) == 1:
            return None
        else:
            return replace(self, stints=self.stints[:-1])

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
    issue: str
    seconds_total: int
    seconds_unpublished: int
    stints_unpublished: int
    last_worked_on: datetime

    @classmethod
    def from_raw(cls: type[Self], name: str, activity: Activity) -> Self:
        return cls(
            name,
            activity.description,
            issue=activity.issue,
            seconds_total=sum(s.seconds() for s in activity.stints),
            seconds_unpublished=sum(
                s.seconds() for s in activity.stints if not s.is_published
            ),
            stints_unpublished=sum(1 for s in activity.stints if not s.is_published),
            last_worked_on=activity.stints[-1].begin,
        )


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
            ActivitySummary.from_raw(name, activity)
            for name, activity in self.activities.items()
            if len(activity.stints) > 0
        )

    def running_activities(self) -> Iterable[tuple[str, Activity]]:
        return (
            (name, activity)
            for (name, activity) in self.activities.items()
            if activity.is_running()
        )

    def update_activity[
        R: Optional[Activity]
    ](self, name: str, func: Callable[[Optional[Activity]], R]) -> R:
        try:
            new_activity = func(self.activities.get(name))
            if new_activity is None:
                self.activities = {
                    k: v for k, v in self.activities.items() if k != name
                }
            else:
                self.activities = {
                    **self.activities,
                    name: new_activity,
                }
            return new_activity
        except ActivityStateError as e:
            raise ActivityUpdateError(name) from e

    async def async_update_activity[
        R: Optional[Activity]
    ](self, name: str, func: Callable[[Optional[Activity]], Awaitable[R]],):
        try:
            new_activity = await func(self.activities.get(name))
            if new_activity is None:
                self.activities = {
                    k: v for k, v in self.activities.items() if k != name
                }
            else:
                self.activities = {
                    **self.activities,
                    name: new_activity,
                }
            return new_activity
        except ActivityStateError as e:
            raise ActivityUpdateError(name) from e
