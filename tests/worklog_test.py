from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from time import sleep
from math import floor, ceil

from pyfakefs.fake_filesystem import FakeFilesystem
from timetracker.worklog.data import Activity, Stint, Worklog
from timetracker.worklog.error import (
    ActivityAlreadyStarted,
    ActivityAlreadyStopped,
    ActivityNeverStarted,
    StintNotFinishedError,
    WorklogDeserializationError,
)
from timetracker.worklog.io import read_from_file, transact
from ward import raises, test, using

from tests import constants
from tests.fixtures import fake_fs

WORKLOG_JSON_PATH = Path("/home/gal/.config/worklog.json")


@test("A stint with only a begin time is unfinished")
def _():
    assert not Stint(begin=constants.BREAKFAST_TIME).is_finished()


@test("A stint with both begin and end time is finished")
def _():
    assert Stint(begin=constants.BREAKFAST_TIME, end=constants.LUNCH_TIME).is_finished()


@test("Finishing an unfinished stint produces a finished one")
def _():
    assert not constants.UNFINISHED_STINT.is_finished()
    finished_stint = constants.UNFINISHED_STINT.finished()
    assert finished_stint.is_finished()
    assert finished_stint is not constants.UNFINISHED_STINT


@test(
    "Finishing a finished stint raises `ActivityAlreadyStopped` and leaves the stint unchanged"
)
def _():
    assert constants.FINISHED_STINT.is_finished()
    with raises(ActivityAlreadyStopped) as ex:
        constants.FINISHED_STINT.finished()
    assert ex.raised.time_last_stopped == constants.FINISHED_STINT.end


@test("The number of seconds in a finished stint can be queried")
def _():
    assert constants.FINISHED_STINT.seconds() == constants.MORNING_SECS


@test(
    "The number of seconds in an unfinished stint can be queried and is based on the current time"
)
def _():
    time_since_begin = datetime.now().astimezone() - constants.UNFINISHED_STINT.begin
    assert constants.UNFINISHED_STINT.seconds() in range(
        floor(time_since_begin.total_seconds()),
        ceil(time_since_begin.total_seconds()) + 1,
    )


@test("An unpublished finished stint can be marked as published")
def _():
    published = constants.FINISHED_STINT.published()
    assert published.is_published
    assert published is not constants.FINISHED_STINT
    assert published.begin == constants.FINISHED_STINT.begin
    assert published.end == constants.FINISHED_STINT.end


@test(
    "Attempting to mark an unfinished stint as published raises `StintNotFinishedError`"
)
def _():
    with raises(StintNotFinishedError):
        constants.UNFINISHED_STINT.published()
    assert not constants.UNFINISHED_STINT.is_published


@test("Marking a published stint as published does nothing")
def _():
    published_again = constants.PUBLISHED_STINT.published()
    assert published_again.is_published
    assert published_again is constants.PUBLISHED_STINT


for stint in [
    constants.UNFINISHED_STINT,
    constants.FINISHED_STINT,
    constants.PUBLISHED_STINT,
]:

    @test(
        "Stints can be serialized to and deserialized from JSON losslessly ({stint!r})"
    )
    def _(stint: Stint = stint):
        json_str = stint.to_json()
        deserialized_stint = Stint.from_json(json_str)
        assert deserialized_stint == stint


@test("A new activity is not running")
def _():
    new_activity = Activity(
        description=constants.NEW_ACTIVITY.description,
        issue=constants.NEW_ACTIVITY.issue,
    )
    assert not new_activity.is_running()
    assert new_activity == constants.NEW_ACTIVITY


@test("Constructing an activity ensures that its stints are sorted")
def _():
    completed_activity = Activity(
        description=constants.COMPLETED_ACTIVITY.description,
        issue=constants.COMPLETED_ACTIVITY.issue,
        stints=constants.COMPLETED_ACTIVITY.stints[::-1],
    )
    assert completed_activity == constants.COMPLETED_ACTIVITY

    running_activity = Activity(
        description=constants.RUNNING_ACTIVITY.description,
        issue=constants.RUNNING_ACTIVITY.issue,
        stints=constants.RUNNING_ACTIVITY.stints[::-1],
    )
    assert running_activity == constants.RUNNING_ACTIVITY


@test("Starting an new activity produces one with an unfinished stint")
def _():
    new_activity = deepcopy(constants.NEW_ACTIVITY)
    started_activity = new_activity.started()
    assert started_activity.is_running()

    match started_activity:
        case Activity(stints=[Stint(end=None)]):
            pass
        case _ as value:
            assert False, f"{repr(value)} does not match the pattern"

    assert new_activity == constants.NEW_ACTIVITY


@test("Restarting an activity produces one with a new unfinished stint")
def _():
    stopped_activity = Activity(
        description="", issue="", stints=(constants.FINISHED_STINT,)
    )
    restarted_activity = stopped_activity.started()
    assert restarted_activity.is_running()

    match restarted_activity:
        case Activity(stints=[constants.FINISHED_STINT, Stint(end=None)]):
            pass
        case _ as value:
            assert False, f"{repr(value)} does not match the pattern"


@test("Starting an activity which is running raises `ActivityAlreadyStarted`")
def _():
    assert constants.RUNNING_ACTIVITY.is_running()

    with raises(ActivityAlreadyStarted) as ex:
        constants.RUNNING_ACTIVITY.started()

    assert constants.RUNNING_ACTIVITY.is_running()
    assert ex.raised.time_last_started == constants.RUNNING_ACTIVITY.stints[-1].begin


@test("Stopping a running activity produces one with a finished stint")
def _():
    running_activity = Activity(
        description="", issue="", stints=(Stint(begin=constants.BREAKFAST_TIME),)
    )
    match running_activity.stopped():
        case Activity(
            stints=[
                Stint(begin=constants.BREAKFAST_TIME, end=datetime()),
            ]
        ):
            pass
        case _ as value:
            assert False, f"{repr(value)} does not match the pattern"

    [running_stint] = running_activity.stints
    assert not running_stint.is_finished()


@test("Stopping an activity which is not running raises an exception")
def _():
    with raises(ActivityNeverStarted):
        constants.NEW_ACTIVITY.stopped()

    with raises(ActivityAlreadyStopped) as ex:
        constants.COMPLETED_ACTIVITY.stopped()
    assert ex.raised.time_last_stopped == constants.COMPLETED_ACTIVITY.stints[-1].end


for activity in [
    constants.NEW_ACTIVITY,
    constants.RUNNING_ACTIVITY,
    constants.COMPLETED_ACTIVITY,
]:

    @test(
        "Activities can be serialized to and deserialized from JSON losslessly ({activity!r})"
    )
    def _(activity: Activity = activity):
        json_str = activity.to_json()
        deserialized_activity = Activity.from_json(json_str)
        assert deserialized_activity == activity


@test("Creating a new worklog starts out without any activities")
def _():
    assert Worklog().activities == {}


@test(
    "Updating a hitherto unknown activity invokes the callback with `None` but create one with the callback's result"
)
def _():
    log = deepcopy(constants.MIXED_WORKLOG)

    received = []
    log.update_activity(
        "secret", lambda a: (received.append(a), constants.ALL_NIGHTER_ACTIVITY)[1]
    )
    assert received == [None]

    assert log.activities == {
        **constants.MIXED_WORKLOG.activities,
        "secret": constants.ALL_NIGHTER_ACTIVITY,
    }


@test("Updating an existing activity replaces its value")
def _():
    log = deepcopy(constants.MIXED_WORKLOG)

    received = []
    log.update_activity(
        "running", lambda a: (received.append(a), constants.ALL_NIGHTER_ACTIVITY)[1]
    )
    assert received == [constants.RUNNING_ACTIVITY]
    assert log.activities == {
        **constants.MIXED_WORKLOG.activities,
        "running": constants.ALL_NIGHTER_ACTIVITY,
    }


for worklog in [Worklog(), constants.MIXED_WORKLOG]:

    @test(
        "Worklogs can be serialized to and deserialized from JSON losslessly ({worklog!r})"
    )
    def _(worklog: Worklog = worklog):
        json_str = worklog.to_json()
        deserialized_worklog = Worklog.from_json(json_str)
        assert deserialized_worklog == worklog


@test(
    "Given a non-existing worklog JSON file, "
    "when entering the transaction context, "
    "then the file is created and an empty worklog is yielded"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_dir(WORKLOG_JSON_PATH.parent)

    with transact(WORKLOG_JSON_PATH) as worklog:
        assert WORKLOG_JSON_PATH.exists()
        assert worklog == Worklog()

    assert read_from_file(WORKLOG_JSON_PATH) == Worklog()


@test(
    "Given that the non-existing worklog JSON file would be located in a read-only directory, "
    "when entering the transaction context, "
    "then `PermissionError` is raised"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_dir(WORKLOG_JSON_PATH.parent)
    WORKLOG_JSON_PATH.parent.chmod(0o555)

    with raises(PermissionError):
        with transact(WORKLOG_JSON_PATH):
            assert False, "context manager suite should not run"


@test(
    "Given that the worklog JSON file is located in a directory that is not readable, "
    "when entering the transaction context, "
    "then `PermissionError` is raised"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_dir(WORKLOG_JSON_PATH.parent)
    WORKLOG_JSON_PATH.parent.chmod(0o277)

    with raises(PermissionError):
        with transact(WORKLOG_JSON_PATH):
            assert False, "context manager suite should not run"


@test(
    "Given that the directory which would hold the worklog JSON file does not exist, "
    "when entering the transaction contxt, "
    "then `FileNotFoundError` is raised"
)
@using(_=fake_fs)
def _(_: FakeFilesystem):
    with raises(FileNotFoundError):
        with transact(WORKLOG_JSON_PATH):
            pass


@test(
    "Given an existing worklog JSON file which is readable, "
    "when entering the transaction context, "
    "then the worklog is read"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_file(
        WORKLOG_JSON_PATH,
        contents=constants.MIXED_WORKLOG.to_json(),
    )

    with transact(WORKLOG_JSON_PATH) as worklog:
        assert worklog == constants.MIXED_WORKLOG


@test(
    "Given an existing worklog JSON file which isn't readable, "
    "when entering the transaction context, "
    "then `PermissionError` is raised"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_file(
        WORKLOG_JSON_PATH,
        contents=constants.MIXED_WORKLOG.to_json(),
    )
    WORKLOG_JSON_PATH.chmod(0o366)

    with raises(PermissionError):
        with transact(WORKLOG_JSON_PATH):
            pass


@test(
    "Given an existing worklog JSON file which is read-writable, "
    "when exiting the transaction context after modifying the worklog, "
    "then the JSON file will be updated"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_file(
        WORKLOG_JSON_PATH,
        contents=constants.MIXED_WORKLOG.to_json(),
    )

    with transact(WORKLOG_JSON_PATH) as worklog:
        worklog.update_activity("running", lambda a: Activity.verify(a).stopped())

    assert Worklog.from_json(WORKLOG_JSON_PATH.read_text()) == worklog


@test(
    "Given an existing worklog JSON file which is read-writable, "
    "when exiting the transaction context after modifying the worklog such that its JSON representation becomes shorter, "
    "then the JSON file will be updated and truncated"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_file(
        WORKLOG_JSON_PATH,
        contents=constants.MIXED_WORKLOG.to_json(indent=2),
    )
    size_before = WORKLOG_JSON_PATH.stat().st_size

    with transact(WORKLOG_JSON_PATH) as worklog:
        worklog.update_activity(
            "running", lambda a: replace(Activity.verify(a), stints=[])
        )

    size_after = WORKLOG_JSON_PATH.stat().st_size
    assert size_after < size_before
    assert Worklog.from_json(WORKLOG_JSON_PATH.read_text()) == worklog


@test(
    "Given an existing worklog JSON file which is read-only, "
    "when exiting the transaction context after modifying the worklog, "
    "then `PermissionError` is raised"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_file(
        WORKLOG_JSON_PATH,
        contents=constants.MIXED_WORKLOG.to_json(),
    )
    WORKLOG_JSON_PATH.chmod(0o444)

    worklog = None
    with raises(PermissionError):
        with transact(WORKLOG_JSON_PATH) as worklog:
            worklog.update_activity("running", lambda a: Activity.verify(a).stopped())

    assert (
        worklog != constants.MIXED_WORKLOG
    ), "worklog should be modified, as exception should only be raised upon exiting the context"


@test(
    "Given an existing worklog JSON file, "
    "when exiting the transaction context without modifying the worklog, "
    "then the JSON file will not be updated"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_file(
        WORKLOG_JSON_PATH,
        contents=constants.MIXED_WORKLOG.to_json(),
    )
    original_mtime = WORKLOG_JSON_PATH.stat().st_mtime
    sleep(0.001)  # sleep 1 ms to ensure mtime is different if file changed

    with transact(WORKLOG_JSON_PATH):
        pass

    assert WORKLOG_JSON_PATH.stat().st_mtime == original_mtime


@test(
    "Given an existing worklog JSON file which is read-only, "
    "when reading the file without a transaction context, "
    "then the worklog is read"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_file(
        WORKLOG_JSON_PATH,
        contents=constants.MIXED_WORKLOG.to_json(),
    )

    assert read_from_file(WORKLOG_JSON_PATH) == constants.MIXED_WORKLOG


@test(
    "Given an existing worklog JSON file which is read-only, "
    "when reading an invalid file, "
    "then `WorklogDeserializationError` is raised"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_file(
        WORKLOG_JSON_PATH,
        contents="{",
    )

    with raises(WorklogDeserializationError):
        read_from_file(WORKLOG_JSON_PATH)


@test(
    "Given an existing worklog JSON file which isn't readable, "
    "when reading the file without a transaction context, "
    "then `PermissionError` is raised"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_file(
        WORKLOG_JSON_PATH,
        contents=constants.MIXED_WORKLOG.to_json(),
    )
    WORKLOG_JSON_PATH.chmod(0o333)

    with raises(PermissionError):
        read_from_file(WORKLOG_JSON_PATH)


@test(
    "Given a non-existing worklog JSON file, "
    "when reading the file without a transaction context, "
    "then `FileNotFoundError` is raised and the file is NOT created"
)
@using(fs=fake_fs)
def _(fs: FakeFilesystem):
    fs.create_dir(WORKLOG_JSON_PATH.parent)

    with raises(FileNotFoundError):
        read_from_file(WORKLOG_JSON_PATH)

    assert not WORKLOG_JSON_PATH.exists()
