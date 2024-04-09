from datetime import datetime

from timetracker.worklog.data import Activity, Stint
from timetracker.worklog.error import (
    ActivityAlreadyStarted,
    ActivityAlreadyStopped,
    ActivityNeverStarted,
)
from ward import raises, test

from tests import constants


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


@test("Finishing a finished stint raises an exception and leaves the stint unchanged")
def _():
    assert constants.FINISHED_STINT.is_finished()
    with raises(ActivityAlreadyStopped) as ex:
        constants.FINISHED_STINT.finished()
    assert ex.raised.time_last_stopped == constants.FINISHED_STINT.end


for stint in [constants.UNFINISHED_STINT, constants.FINISHED_STINT]:

    @test(
        "Stints can be serialized to and deserialized from JSON losslessly ({stint!r})"
    )
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
    stopped_activity = Activity(stints=[constants.FINISHED_STINT])
    restarted_activity = stopped_activity.started()
    assert restarted_activity.is_running()

    match restarted_activity:
        case Activity(stints=[constants.FINISHED_STINT, Stint(end=None)]):
            pass
        case _ as value:
            assert False, f"{repr(value)} does not match the pattern"


@test("Starting an activity which is running raises an exception")
def _():
    assert constants.RUNNING_ACTIVITY.is_running()

    with raises(ActivityAlreadyStarted) as ex:
        constants.RUNNING_ACTIVITY.started()

    assert constants.RUNNING_ACTIVITY.is_running()
    assert ex.raised.time_last_started == constants.RUNNING_ACTIVITY.stints[-1].begin


@test("Stopping a running activity produces one with a finished stint")
def _():
    running_activity = Activity(stints=[Stint(begin=constants.BREAKFAST_TIME)])
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
        Activity().stopped()

    with raises(ActivityAlreadyStopped) as ex:
        constants.COMPLETED_ACTIVITY.stopped()
    assert ex.raised.time_last_stopped == constants.COMPLETED_ACTIVITY.stints[-1].end


for activity in [Activity(), constants.RUNNING_ACTIVITY, constants.COMPLETED_ACTIVITY]:

    @test(
        "Activities can be serialized to and deserialized from JSON losslessly ({activity!r})"
    )
    def _(activity: Activity = activity):
        json_str = activity.to_json()
        deserialized_activity = Activity.from_json(json_str)
        assert deserialized_activity == activity
