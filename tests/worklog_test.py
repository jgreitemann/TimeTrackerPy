from datetime import datetime

from timetracker.worklog.data import Activity, Stint
from timetracker.worklog.error import (
    ActivityAlreadyStarted,
    ActivityAlreadyStopped,
    ActivityNeverStarted,
)
from ward import raises, test

from tests import constants


@test("A stint with only a start time is unfinished")
def _():
    assert not Stint(start=constants.BREAKFAST_TIME).is_finished()


@test("A stint with both start and end time is finished")
def _():
    assert Stint(start=constants.BREAKFAST_TIME, end=constants.LUNCH_TIME).is_finished()


@test("Finishing an unfinished stint produces a finished one")
def _():
    unfinished_stint = Stint(start=constants.BREAKFAST_TIME)
    finished_stint = unfinished_stint.finished()
    assert finished_stint.is_finished()
    assert finished_stint is not unfinished_stint
    assert not unfinished_stint.is_finished()


@test("Finishing a finished stint raises an exception and leaves the stint unchanged")
def _():
    finished_stint = Stint(start=constants.BREAKFAST_TIME, end=constants.LUNCH_TIME)
    with raises(ActivityAlreadyStopped) as ex:
        finished_stint.finished()
    assert ex.raised.time_last_stopped == constants.LUNCH_TIME
    assert finished_stint.end == constants.LUNCH_TIME


for stint in [
    Stint(start=constants.BREAKFAST_TIME),
    Stint(start=constants.BREAKFAST_TIME, end=constants.LUNCH_TIME),
]:

    @test("Stints can be serialized to and deserialized from JSON losslessly ({stint})")
    def _(stint: Stint = stint):
        json_str = stint.to_json()
        deserialized_stint = Stint.from_json(json_str)
        assert deserialized_stint == stint


@test("A new activity is not running")
def _():
    assert not Activity().is_running()


@test("Starting an new activity produces one with an unfinished stint")
def _():
    new_activity = Activity()
    started_activity = new_activity.started()
    assert started_activity.is_running()

    match started_activity:
        case Activity(stints=[Stint(end=None)]):
            pass
        case _ as value:
            assert False, f"{repr(value)} does not match the pattern"

    assert new_activity == Activity()


@test("Restarting an activity produces one with a new unfinished stint")
def _():
    stopped_activity = Activity(
        stints=[Stint(start=constants.BREAKFAST_TIME, end=constants.LUNCH_TIME)]
    )
    restarted_activity = stopped_activity.started()
    assert restarted_activity.is_running()

    match restarted_activity:
        case Activity(
            stints=[
                Stint(start=constants.BREAKFAST_TIME, end=constants.LUNCH_TIME),
                Stint(end=None),
            ]
        ):
            pass
        case _ as value:
            assert False, f"{repr(value)} does not match the pattern"


@test("Starting an activity which is running raises an exception")
def _():
    running_activity = Activity().started()

    with raises(ActivityAlreadyStarted) as ex:
        running_activity.started()

    [running_stint] = running_activity.stints
    assert not running_stint.is_finished()

    assert ex.raised.time_last_started == running_stint.start


@test("Stopping a running activity produces one with a finished stint")
def _():
    running_activity = Activity(stints=[Stint(start=constants.BREAKFAST_TIME)])
    match running_activity.stopped():
        case Activity(
            stints=[
                Stint(start=constants.BREAKFAST_TIME, end=datetime()),
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
        Activity().stopped()

    with raises(ActivityAlreadyStopped) as ex:
        Activity(
            stints=[Stint(start=constants.BREAKFAST_TIME, end=constants.LUNCH_TIME)]
        ).stopped()
    assert ex.raised.time_last_stopped == constants.LUNCH_TIME
